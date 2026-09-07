"""Reversible v2 publication including recovery of qualifying v1 exclusions.

Caller stops playback and every library writer. Verify the complete inventory and
each MIDI/sidecar hash before any move. Originals remain byte-identical.
"""

from datetime import datetime, timezone
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3

from .curation_transaction import _write
from .quality import VERSION


def inventory(root):
    return {p.relative_to(root).as_posix() for p in root.glob("assets/*.json")} | {
        p.relative_to(root).as_posix() for p in root.glob("archive/*/assets/*.json")
    }


def location(root, entry):
    relative = entry["original_location"]
    if not re.fullmatch(r"(?:assets|archive/[A-Za-z0-9_.-]+/assets)/[a-f0-9]{64}\.json", relative):
        raise ValueError("unsafe original location")
    path = root / relative
    if root not in path.resolve().parents or path.is_symlink():
        raise ValueError("original escapes library")
    if "sha256:" + path.stem != entry["asset_id"]:
        raise ValueError("location identity mismatch")
    return path


def restore_files(root, run, plan):
    for entry in reversed(plan["entries"]):
        original = location(root, entry)
        moved = destination(root, run, entry)
        if original == moved:
            continue
        for suffix in (".mid", ".json"):
            source = moved.with_suffix(suffix)
            target = original.with_suffix(suffix)
            if source.exists():
                if target.exists():
                    raise RuntimeError("rollback collision")
                source.replace(target)
    for name in ("listening-admission.json", "catalog.db", "quality.sqlite3"):
        before = run / (name + ".before")
        if before.exists():
            _write(root / name, before.read_bytes())
        elif name == "quality.sqlite3":
            (root / name).unlink(missing_ok=True)
    _write(run / "state.json", b'{"state":"restored"}\n')


def destination(root, run, entry):
    original = location(root, entry)
    if entry["status"] == "qualified":
        return root / "assets" / original.name
    if entry["original_location"].startswith("assets/"):
        return run / "assets" / original.name
    return original


def apply(root: Path, plan: dict) -> Path:
    from .catalog import rebuild_catalog

    root = root.resolve()
    if plan.get("policy_version") != VERSION:
        raise ValueError("wrong quality policy")
    entries = plan["entries"]
    if len({e["asset_id"] for e in entries}) != len(entries):
        raise ValueError("duplicate plan identities")
    if {e["original_location"] for e in entries} != inventory(root):
        raise ValueError("inventory changed after scan")
    lock = root / ".curation-lock"
    lock.mkdir()
    run = root / "archive" / ("quality-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ"))
    try:
        for entry in entries:
            path = location(root, entry)
            for suffix, expected in ((".mid", path.stem), (".json", entry["sidecar_sha256"])):
                item = path.with_suffix(suffix)
                if item.is_symlink() or hashlib.sha256(item.read_bytes()).hexdigest() != expected:
                    raise ValueError("source changed: " + item.name)
            if entry["status"] == "qualified" and (entry["reasons"] or not entry["evidence"]):
                raise ValueError("qualified entry lacks evidence or has blocking reasons")
            target = destination(root, run, entry)
            if path != target and any(target.with_suffix(s).exists() for s in (".mid", ".json")):
                raise ValueError("destination collision")
        run.mkdir()
        (run / "assets").mkdir()
        (run / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
        shutil.copyfile(root / "listening-admission.json", run / "listening-admission.json.before")
        for name in ("catalog.db", "quality.sqlite3"):
            if (root / name).exists():
                with (
                    closing(sqlite3.connect(root / name)) as src,
                    closing(sqlite3.connect(run / (name + ".before"))) as dst,
                ):
                    src.backup(dst)
        _write(run / "state.json", b'{"state":"prepared"}\n')
        try:
            for entry in entries:
                original = location(root, entry)
                target = destination(root, run, entry)
                if original != target:
                    for suffix in (".mid", ".json"):
                        if target.with_suffix(suffix).exists():
                            raise ValueError("destination collision")
                        original.with_suffix(suffix).replace(target.with_suffix(suffix))
            ids = sorted(e["asset_id"] for e in entries if e["status"] == "qualified")
            manifest = {
                "policy_version": VERSION,
                "run": run.name,
                "asset_ids": ids,
                "decision_plan_sha256": hashlib.sha256(
                    (run / "plan.json").read_bytes()
                ).hexdigest(),
            }
            _write(root / "listening-admission.json", json.dumps(manifest).encode())
            temp = run / "quality.new.sqlite3"
            with closing(sqlite3.connect(temp)) as conn, conn:
                conn.execute(
                    "CREATE TABLE quality (asset_id TEXT PRIMARY KEY, record TEXT NOT NULL)"
                )
                conn.executemany(
                    "INSERT INTO quality VALUES (?,?)",
                    [
                        (e["asset_id"], json.dumps(e["display"]))
                        for e in entries
                        if e["status"] == "qualified"
                    ],
                )
            _write(root / "quality.sqlite3", temp.read_bytes())
            report = rebuild_catalog(root)
            if report.indexed_assets != len(ids):
                raise RuntimeError("admitted catalog count mismatch")
            _write(run / "state.json", b'{"state":"committed"}\n')
        except BaseException:
            restore_files(root, run, plan)
            raise
    finally:
        lock.rmdir()
    return run


def restore(root: Path, run: Path) -> None:
    root, run = root.resolve(), run.resolve()
    if run.parent != root / "archive":
        raise ValueError("wrong archive directory")
    manifest = json.loads((root / "listening-admission.json").read_bytes())
    if manifest.get("run") != run.name:
        raise ValueError("only the current publication can be restored")
    plan = json.loads((run / "plan.json").read_bytes())
    expected = {destination(root, run, e).relative_to(root).as_posix() for e in plan["entries"]}
    if inventory(root) != expected:
        raise ValueError("library inventory changed since publication")
    for entry in plan["entries"]:
        path = destination(root, run, entry)
        for suffix, digest in ((".mid", path.stem), (".json", entry["sidecar_sha256"])):
            if hashlib.sha256(path.with_suffix(suffix).read_bytes()).hexdigest() != digest:
                raise ValueError("library content changed since publication")
    lock = root / ".curation-lock"
    lock.mkdir()
    try:
        restore_files(root, run, plan)
    finally:
        lock.rmdir()
