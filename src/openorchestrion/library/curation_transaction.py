"""Reversible publication of a validated curation plan while playback is stopped."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3

from .curation import ADMISSION_FILE, POLICY_VERSION


def _write(path: Path, data: bytes) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(data)
    os.replace(temporary, path)


def _restore(root: Path, run: Path, plan: dict) -> None:
    for entry in plan["entries"]:
        if not entry["reasons"]:
            continue
        digest = entry["asset_id"].removeprefix("sha256:")
        for suffix in (".mid", ".json"):
            archived = run / "assets" / (digest + suffix)
            target = root / "assets" / archived.name
            if archived.exists():
                if target.exists():
                    raise RuntimeError(f"restore collision: {target}")
                os.replace(archived, target)
    previous = run / "admission.before.json"
    if previous.exists():
        _write(root / ADMISSION_FILE, previous.read_bytes())
    else:
        (root / ADMISSION_FILE).unlink(missing_ok=True)
    _write(root / "catalog.db", (run / "catalog.before.db").read_bytes())
    _write(run / "state.json", b'{"state":"restored"}\n')


def apply_plan(root: Path, plan: dict, *, run_name: str | None = None) -> Path:
    """Publish or roll back on failure. Caller must stop all library writers/playback."""
    from .catalog import rebuild_catalog

    root = root.resolve()
    current_manifest = root / ADMISSION_FILE
    if current_manifest.exists() and json.loads(current_manifest.read_bytes()).get('policy_version') == 'complete-listening-v2':
        raise ValueError('v1 curation cannot replace the complete-listening-v2 policy')
    if plan.get("policy_version") != POLICY_VERSION or Path(plan["library_root"]).resolve() != root:
        raise ValueError("plan belongs to a different library or policy")
    entries = plan["entries"]
    identities = [e["asset_id"] for e in entries]
    if len(identities) != len(set(identities)) or any(
            not re.fullmatch(r"sha256:[0-9a-f]{64}", x) for x in identities):
        raise ValueError("invalid or duplicate plan identity")
    if set(identities) != {"sha256:" + p.stem for p in (root / "assets").glob("*.json")}:
        raise ValueError("library inventory changed after scan")
    name = run_name or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name) or name in {".", ".."}:
        raise ValueError("invalid archive run name")
    run = root / "archive" / name
    if root not in run.resolve().parents:
        raise ValueError("archive escapes library")
    lock = root / ".curation-lock"
    lock.mkdir()
    try:
        # Validate every input before moving the first file or publishing policy.
        for entry in entries:
            digest = entry["asset_id"].removeprefix("sha256:")
            for suffix, expected in ((".mid", digest), (".json", entry["sidecar_sha256"])):
                path = root / "assets" / (digest + suffix)
                if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                    raise ValueError(f"input changed after scan: {path.name}")
        run.mkdir(parents=True, exist_ok=False)
        (run / "assets").mkdir()
        (run / "plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
        if (root / ADMISSION_FILE).exists():
            shutil.copyfile(root / ADMISSION_FILE, run / "admission.before.json")
        with sqlite3.connect(root / "catalog.db") as source, sqlite3.connect(run / "catalog.before.db") as backup:
            source.backup(backup)
        _write(run / "state.json", b'{"state":"prepared"}\n')
        try:
            for entry in entries:
                if not entry["reasons"]:
                    continue
                digest = entry["asset_id"].removeprefix("sha256:")
                for suffix in (".mid", ".json"):
                    os.replace(root / "assets" / (digest + suffix), run / "assets" / (digest + suffix))
            admitted = {e["asset_id"] for e in entries if not e["reasons"]}
            old = run / "admission.before.json"
            if old.exists():
                # Existing admitted files remain physically present and were in
                # this scan; previously archived files are never reintroduced.
                admitted &= set(identities)
            manifest = {"policy_version": POLICY_VERSION, "run": name, "asset_ids": sorted(admitted)}
            _write(root / ADMISSION_FILE, (json.dumps(manifest) + "\n").encode())
            result = rebuild_catalog(root)
            if result.indexed_assets != len(admitted):
                raise RuntimeError("published catalog count differs from admission plan")
            _write(run / "state.json", b'{"state":"committed"}\n')
        except BaseException:
            _restore(root, run, plan)
            raise
    finally:
        lock.rmdir()
    return run


def restore_run(root: Path, run: Path) -> None:
    """Undo the most recent unchanged publication; refuse to overwrite newer data."""
    root, run = root.resolve(), run.resolve()
    if run.parent != root / "archive":
        raise ValueError("archive run must be directly inside this library")
    manifest = json.loads((root / ADMISSION_FILE).read_text())
    if manifest.get("run") != run.name:
        raise ValueError("restore must target the currently published run")
    plan = json.loads((run / "plan.json").read_text())
    # Restoring the old catalog would lose later metadata/import changes. Compare
    # all original sidecars and reject any additions before restoring anything.
    expected_active = {e["asset_id"].removeprefix("sha256:") for e in plan["entries"] if not e["reasons"]}
    if {p.stem for p in (root / "assets").glob("*.json")} != expected_active:
        raise ValueError("active library changed since publication")
    for entry in plan["entries"]:
        digest = entry["asset_id"].removeprefix("sha256:")
        base = run if entry["reasons"] else root
        if hashlib.sha256((base / "assets" / (digest + ".json")).read_bytes()).hexdigest() != entry["sidecar_sha256"]:
            raise ValueError("metadata changed since publication")
    lock = root / ".curation-lock"
    lock.mkdir()
    try:
        _restore(root, run, plan)
    finally:
        lock.rmdir()
