"""Additive, restart-free publication with a durable roll-forward journal.

Existing assets and metadata are never rewritten. An interrupted publication is
reconciled before the next scan. The catalog is updated only after qualification
and admission are durable, so partially copied files cannot become playable.
"""

from contextlib import closing
import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path
import re
import sqlite3

from .catalog import reindex_asset
from .quality import VERSION


def _write(path, data):
    """Persist bytes and directory entry before exposing dependent state."""
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    if os.name == "posix":
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def process_identity(pid):
    return (
        Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19],
    )


@contextmanager
def snapshot_lock(root):
    """Keep the acquisition ledger and library coherent during backup snapshots."""
    try:
        import fcntl
    except ImportError:
        # Automatic acquisition is Linux-only; Windows can still restore backups.
        yield
        return
    with (root / ".acquisition-snapshot.lock").open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(
                "library acquisition or backup snapshot is running; retry later"
            ) from exc
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


@contextmanager
def publication_lock(root):
    # A symlink publishes the complete owner identity atomically. Full curation's
    # mkdir on the same path refuses it, and we never remove unknown legacy locks.
    lock = root / ".curation-lock"
    pid = os.getpid()
    boot, start = process_identity(pid)
    owner = f"acquisition-{pid}-{boot}-{start}"
    try:
        lock.symlink_to(owner)
    except FileExistsError:
        if not lock.is_symlink():
            raise RuntimeError("another library operation holds the curation lock")
        previous = os.readlink(lock)
        match = re.fullmatch(r"acquisition-(\d+)-([a-f0-9-]+)-(\d+)", previous)
        if not match:
            raise RuntimeError("unknown curation lock owner")
        try:
            alive = process_identity(int(match[1])) == (match[2], match[3])
        except FileNotFoundError:
            alive = False
        if alive:
            raise RuntimeError("another acquisition publication is running")
        lock.unlink()
        lock.symlink_to(owner)
    try:
        yield
    finally:
        if lock.is_symlink() and os.readlink(lock) == owner:
            lock.unlink()


def publish(root: Path, journal: Path, record: dict | None = None):
    root = root.resolve()
    is_new = record is not None
    if record is None:
        record = json.loads(journal.read_bytes())
    if record.get("status") != "qualified" or record.get("reasons") or not record.get("evidence"):
        raise ValueError("candidate is not qualified")
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", record["asset_id"]):
        raise ValueError("invalid candidate identity")
    if is_new:
        _write(journal, json.dumps(record).encode())
    asset = record["asset_id"]
    digest = asset[7:]
    source = Path(record["stage"])
    with publication_lock(root):
        manifest_path = root / "listening-admission.json"
        manifest = json.loads(manifest_path.read_bytes())
        if manifest.get("policy_version") != VERSION:
            raise ValueError("nightly acquisition requires the v2 admission policy")
        if any(root.glob("archive/*/assets/" + digest + ".json")):
            raise ValueError("candidate already exists in recovery archive")
        for suffix, expected in ((".mid", digest), (".json", record["sidecar_sha256"])):
            raw = source.with_suffix(suffix).read_bytes()
            if hashlib.sha256(raw).hexdigest() != expected:
                raise ValueError("staged candidate changed")
            target = root / "assets" / (digest + suffix)
            if target.is_symlink():
                raise ValueError("publication target is a symlink")
            if target.exists():
                if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
                    raise ValueError("existing asset collision; refusing to overwrite")
            else:
                _write(target, raw)
        with closing(sqlite3.connect(root / "quality.sqlite3", timeout=20)) as conn, conn:
            conn.execute(
                "INSERT OR IGNORE INTO quality(asset_id,record) VALUES (?,?)",
                (asset, json.dumps(record["display"])),
            )
        manifest["asset_ids"] = sorted(set(manifest["asset_ids"]) | {asset})
        # Keep the initial decision-plan identity; additive changes have their own journal.
        manifest["latest_acquisition"] = journal.stem
        _write(manifest_path, json.dumps(manifest).encode())
        if not reindex_asset(root / "catalog.db", root, asset):
            raise RuntimeError("catalog is unavailable; publication will resume next run")
        record["published"] = True
        _write(journal, json.dumps(record).encode())
    return record
