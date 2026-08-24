"""Verified application-data backup and restore for OpenOrchestrion.

This module backs up the durable appliance state, not the software installation:
content-addressed MIDI objects, their authoritative sidecars, and a database-safe
snapshot of listening history.  ``catalog.db`` is intentionally omitted because
it is rebuilt from sidecars during restore.

The core restore operation publishes only into an absent or empty state root.
Stopping/replacing a live appliance and restoring configuration/secrets belong to
a later operator/CLI layer, not to this filesystem primitive.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import tempfile
import zipfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, Iterable
from uuid import uuid4

from .library.catalog import CatalogError, rebuild_catalog

BACKUP_FORMAT = "openorchestrion-application-data"
BACKUP_VERSION = 1
MANIFEST_PATH = "manifest.json"
_HISTORY_PATH = "history.db"
_ASSET_RE = re.compile(r"^library/assets/([0-9a-f]{64})\.(mid|json)$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_COPY_CHUNK = 1024 * 1024


class BackupError(ValueError):
    """Backup input is inconsistent or cannot be safely represented."""


class RestoreError(ValueError):
    """A backup archive is invalid or cannot be safely restored."""


@dataclass(frozen=True, slots=True)
class BackupFile:
    path: str
    size_bytes: int
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class BackupResult:
    archive_path: str
    created_at: str
    asset_count: int
    history_included: bool
    files: tuple[BackupFile, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "archive_path": self.archive_path,
            "created_at": self.created_at,
            "asset_count": self.asset_count,
            "history_included": self.history_included,
            "files": [entry.to_dict() for entry in self.files],
        }


@dataclass(frozen=True, slots=True)
class RestoreResult:
    state_root: str
    asset_count: int
    history_restored: bool
    catalog_path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(_COPY_CHUNK):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _stream_to_zip(
    archive: zipfile.ZipFile,
    source: Path,
    archive_path: str,
) -> BackupFile:
    """Copy once into the archive while hashing exactly the bytes being stored."""
    digest = hashlib.sha256()
    size = 0
    with source.open("rb") as input_handle, archive.open(archive_path, "w") as output:
        while chunk := input_handle.read(_COPY_CHUNK):
            output.write(chunk)
            digest.update(chunk)
            size += len(chunk)
    return BackupFile(path=archive_path, size_bytes=size, sha256=digest.hexdigest())


def _fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    """Best-effort directory fsync for durable rename publication on POSIX."""
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _asset_pairs(library_root: Path) -> tuple[tuple[str, Path, Path], ...]:
    assets = library_root / "assets"
    if not assets.is_dir():
        raise BackupError(f"library assets directory does not exist: {assets}")

    midis = {path.stem: path for path in assets.glob("*.mid") if path.is_file()}
    sidecars = {path.stem: path for path in assets.glob("*.json") if path.is_file()}

    missing_sidecars = sorted(set(midis) - set(sidecars))
    missing_midis = sorted(set(sidecars) - set(midis))
    if missing_sidecars:
        raise BackupError(f"MIDI object(s) missing sidecar: {', '.join(missing_sidecars)}")
    if missing_midis:
        raise BackupError(f"sidecar(s) missing MIDI object: {', '.join(missing_midis)}")

    pairs: list[tuple[str, Path, Path]] = []
    for digest in sorted(midis):
        if not _DIGEST_RE.fullmatch(digest):
            raise BackupError(f"asset filename is not a SHA-256 digest: {digest}")
        midi = midis[digest]
        sidecar = sidecars[digest]
        if midi.is_symlink() or sidecar.is_symlink():
            raise BackupError(f"asset pair must not contain symlinks: {digest}")

        actual_digest, _ = _sha256_file(midi)
        if actual_digest != digest:
            raise BackupError(
                f"content-addressed MIDI {midi.name} hashes to {actual_digest}; refusing backup"
            )
        try:
            document = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BackupError(f"cannot read sidecar {sidecar}: {exc}") from exc
        if not isinstance(document, dict):
            raise BackupError(f"sidecar is not a JSON object: {sidecar}")
        file_info = document.get("file") or {}
        if document.get("asset_id") != f"sha256:{digest}":
            raise BackupError(f"{sidecar}: asset_id does not match filename digest")
        if file_info.get("sha256") != digest:
            raise BackupError(f"{sidecar}: file.sha256 does not match filename digest")
        if file_info.get("stored_filename") != f"{digest}.mid":
            raise BackupError(f"{sidecar}: stored_filename does not match filename digest")
        pairs.append((digest, midi, sidecar))
    return tuple(pairs)


def _validate_library_without_mutating(library_root: Path) -> int:
    """Reuse strict catalog indexing rules, but write the validation DB elsewhere."""
    pairs = _asset_pairs(library_root)
    with tempfile.TemporaryDirectory(prefix="openorchestrion-backup-catalog-") as temp:
        try:
            result = rebuild_catalog(
                library_root,
                db_path=Path(temp) / "catalog.db",
                strict=True,
            )
        except (CatalogError, OSError, ValueError) as exc:
            raise BackupError(f"library validation failed: {exc}") from exc
    if result.indexed_assets != len(pairs):
        raise BackupError(
            f"library validation indexed {result.indexed_assets} assets, expected {len(pairs)}"
        )
    return len(pairs)


def _validate_sqlite(path: Path, *, error_type: type[ValueError]) -> None:
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            row = connection.execute("PRAGMA quick_check").fetchone()
        finally:
            connection.close()
    except sqlite3.Error as exc:
        raise error_type(f"invalid SQLite database {path.name}: {exc}") from exc
    if row is None or row[0] != "ok":
        detail = None if row is None else row[0]
        raise error_type(f"SQLite quick_check failed for {path.name}: {detail}")


def _snapshot_history(source: Path, destination: Path) -> None:
    if source.is_symlink():
        raise BackupError("history.db must not be a symlink")
    try:
        source_connection = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
        target_connection = sqlite3.connect(destination)
        try:
            source_connection.backup(target_connection)
            target_connection.commit()
        finally:
            target_connection.close()
            source_connection.close()
    except sqlite3.Error as exc:
        destination.unlink(missing_ok=True)
        raise BackupError(f"could not snapshot history.db: {exc}") from exc
    _validate_sqlite(destination, error_type=BackupError)


def create_backup(
    state_root: str | Path,
    archive_path: str | Path,
) -> BackupResult:
    """Create an atomic, verified application-data backup archive."""
    root = Path(state_root).resolve()
    library = root / "library"
    asset_count = _validate_library_without_mutating(library)
    pairs = _asset_pairs(library)

    destination = Path(archive_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    created_at = datetime.now(UTC).isoformat()

    with tempfile.TemporaryDirectory(prefix="openorchestrion-backup-history-") as temp:
        history_source = root / _HISTORY_PATH
        history_snapshot: Path | None = None
        if history_source.exists():
            if not history_source.is_file():
                raise BackupError(f"history path is not a regular file: {history_source}")
            history_snapshot = Path(temp) / _HISTORY_PATH
            _snapshot_history(history_source, history_snapshot)

        files: list[BackupFile] = []
        try:
            with zipfile.ZipFile(
                temporary,
                mode="w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=6,
                allowZip64=True,
            ) as archive:
                for digest, midi, sidecar in pairs:
                    files.append(
                        _stream_to_zip(archive, midi, f"library/assets/{digest}.mid")
                    )
                    files.append(
                        _stream_to_zip(archive, sidecar, f"library/assets/{digest}.json")
                    )
                if history_snapshot is not None:
                    files.append(_stream_to_zip(archive, history_snapshot, _HISTORY_PATH))

                manifest = {
                    "format": BACKUP_FORMAT,
                    "version": BACKUP_VERSION,
                    "created_at": created_at,
                    "asset_count": asset_count,
                    "history_included": history_snapshot is not None,
                    "files": [entry.to_dict() for entry in sorted(files, key=lambda item: item.path)],
                }
                archive.writestr(
                    MANIFEST_PATH,
                    json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                )
            _fsync_file(temporary)
            os.replace(temporary, destination)
            _fsync_directory(destination.parent)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise

    ordered = tuple(sorted(files, key=lambda item: item.path))
    return BackupResult(
        archive_path=str(destination),
        created_at=created_at,
        asset_count=asset_count,
        history_included=history_snapshot is not None,
        files=ordered,
    )


def _safe_member_name(name: str) -> str:
    if not name or "\\" in name:
        raise RestoreError(f"unsafe archive member path: {name!r}")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise RestoreError(f"unsafe archive member path: {name!r}")
    normalized = str(path)
    if normalized != name:
        raise RestoreError(f"non-canonical archive member path: {name!r}")
    return normalized


def _member_is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = info.external_attr >> 16
    return mode != 0 and stat.S_ISLNK(mode)


def _allowed_data_member(name: str) -> bool:
    return name == _HISTORY_PATH or _ASSET_RE.fullmatch(name) is not None


def _read_manifest(archive: zipfile.ZipFile, infos: dict[str, zipfile.ZipInfo]) -> dict[str, Any]:
    info = infos.get(MANIFEST_PATH)
    if info is None:
        raise RestoreError("backup archive has no manifest.json")
    if info.file_size > 16 * 1024 * 1024:
        raise RestoreError("manifest.json is unreasonably large")
    try:
        document = json.loads(archive.read(info).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RuntimeError, zipfile.BadZipFile) as exc:
        raise RestoreError(f"cannot read manifest.json: {exc}") from exc
    if not isinstance(document, dict):
        raise RestoreError("manifest.json must contain one JSON object")
    if document.get("format") != BACKUP_FORMAT:
        raise RestoreError(f"unsupported backup format: {document.get('format')!r}")
    if document.get("version") != BACKUP_VERSION:
        raise RestoreError(f"unsupported backup version: {document.get('version')!r}")
    return document


def _manifest_files(document: dict[str, Any]) -> dict[str, BackupFile]:
    raw_files = document.get("files")
    if not isinstance(raw_files, list):
        raise RestoreError("manifest files must be an array")
    entries: dict[str, BackupFile] = {}
    for raw in raw_files:
        if not isinstance(raw, dict):
            raise RestoreError("manifest file entry must be an object")
        path = _safe_member_name(raw.get("path") if isinstance(raw.get("path"), str) else "")
        if not _allowed_data_member(path):
            raise RestoreError(f"manifest contains unexpected data path: {path}")
        if path in entries:
            raise RestoreError(f"manifest contains duplicate path: {path}")
        size = raw.get("size_bytes")
        digest = raw.get("sha256")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise RestoreError(f"manifest has invalid size for {path}")
        if not isinstance(digest, str) or not _DIGEST_RE.fullmatch(digest):
            raise RestoreError(f"manifest has invalid SHA-256 for {path}")
        entries[path] = BackupFile(path=path, size_bytes=size, sha256=digest)
    return entries


def _inspect_archive(
    archive: zipfile.ZipFile,
) -> tuple[dict[str, zipfile.ZipInfo], dict[str, BackupFile], dict[str, Any]]:
    infos: dict[str, zipfile.ZipInfo] = {}
    for info in archive.infolist():
        name = _safe_member_name(info.filename)
        if name in infos:
            raise RestoreError(f"backup archive contains duplicate member: {name}")
        if info.is_dir():
            raise RestoreError(f"backup archive contains unexpected directory member: {name}")
        if _member_is_symlink(info):
            raise RestoreError(f"backup archive contains symlink: {name}")
        if info.flag_bits & 0x1:
            raise RestoreError(f"encrypted archive members are not supported: {name}")
        if name != MANIFEST_PATH and not _allowed_data_member(name):
            raise RestoreError(f"backup archive contains unexpected member: {name}")
        infos[name] = info

    manifest = _read_manifest(archive, infos)
    expected = _manifest_files(manifest)
    actual_data = set(infos) - {MANIFEST_PATH}
    if actual_data != set(expected):
        missing = sorted(set(expected) - actual_data)
        extra = sorted(actual_data - set(expected))
        raise RestoreError(f"manifest/archive member mismatch: missing={missing}, extra={extra}")

    for path, entry in expected.items():
        if infos[path].file_size != entry.size_bytes:
            raise RestoreError(f"ZIP size does not match manifest for {path}")
    return infos, expected, manifest


def _extract_verified(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    expected: BackupFile,
    stage: Path,
) -> None:
    destination = stage.joinpath(*PurePosixPath(expected.path).parts)
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    try:
        with archive.open(info, "r") as source, destination.open("xb") as target:
            while chunk := source.read(_COPY_CHUNK):
                target.write(chunk)
                digest.update(chunk)
                size += len(chunk)
            target.flush()
            os.fsync(target.fileno())
    except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
        raise RestoreError(f"could not extract {expected.path}: {exc}") from exc
    if size != expected.size_bytes or digest.hexdigest() != expected.sha256:
        raise RestoreError(f"content digest/size mismatch for {expected.path}")


def _target_is_empty(path: Path) -> bool:
    return path.is_dir() and next(path.iterdir(), None) is None


def restore_backup(
    archive_path: str | Path,
    state_root: str | Path,
) -> RestoreResult:
    """Validate and atomically publish a backup into an absent/empty state root."""
    source = Path(archive_path).resolve()
    target = Path(state_root).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if target.exists() and not _target_is_empty(target):
        raise RestoreError(f"restore target must be absent or empty: {target}")

    target.parent.mkdir(parents=True, exist_ok=True)
    stage = target.parent / f".{target.name}.restore.{uuid4().hex}"
    stage.mkdir(mode=0o750)
    target_existed_empty = target.exists()

    history_present = False
    asset_count = 0
    try:
        try:
            archive = zipfile.ZipFile(source, mode="r")
        except (OSError, zipfile.BadZipFile) as exc:
            raise RestoreError(f"cannot open backup archive: {exc}") from exc
        with archive:
            infos, expected, manifest = _inspect_archive(archive)
            for name in sorted(expected):
                _extract_verified(archive, infos[name], expected[name], stage)

        library = stage / "library"
        try:
            asset_count = _validate_library_without_mutating(library)
        except BackupError as exc:
            raise RestoreError(str(exc)) from exc

        declared_count = manifest.get("asset_count")
        if isinstance(declared_count, bool) or not isinstance(declared_count, int):
            raise RestoreError("manifest asset_count must be an integer")
        if declared_count != asset_count:
            raise RestoreError(
                f"manifest asset_count {declared_count} does not match restored {asset_count}"
            )

        history = stage / _HISTORY_PATH
        history_present = history.is_file()
        if bool(manifest.get("history_included")) != history_present:
            raise RestoreError("manifest history_included does not match archive contents")
        if history_present:
            _validate_sqlite(history, error_type=RestoreError)

        # A restored state becomes usable only when its disposable search index
        # has been rebuilt. Do this in staging so a rebuild failure publishes
        # nothing at all.
        try:
            rebuild_catalog(library, strict=True)
        except (CatalogError, OSError, ValueError) as exc:
            raise RestoreError(f"catalog rebuild failed: {exc}") from exc

        if target_existed_empty:
            target.rmdir()
        try:
            os.replace(stage, target)
        except BaseException:
            if target_existed_empty and not target.exists():
                target.mkdir(mode=0o750)
            raise
        _fsync_directory(target.parent)
    except BaseException:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        raise

    return RestoreResult(
        state_root=str(target),
        asset_count=asset_count,
        history_restored=history_present,
        catalog_path=str(target / "library" / "catalog.db"),
    )


__all__ = [
    "BACKUP_FORMAT",
    "BACKUP_VERSION",
    "BackupError",
    "BackupFile",
    "BackupResult",
    "RestoreError",
    "RestoreResult",
    "create_backup",
    "restore_backup",
]
