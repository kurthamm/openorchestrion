"""Verified application-data backup and restore.

The appliance software is disposable. This module preserves the state that is
not: immutable content-addressed MIDI objects, durable sidecars, and listening
history. ``catalog.db`` is deliberately absent from the archive because it is a
rebuildable index and is regenerated from restored sidecars before publication.

Backups are self-describing ZIP archives with a versioned manifest. Restore
never calls ``extractall``: every member is treated as untrusted input, streamed
to a sibling staging directory, verified, indexed, and only then atomically
published as the requested state root.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import stat
import tempfile
import zipfile
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, Iterable
from uuid import uuid4

from .history import HISTORY_SCHEMA_VERSION
from .library.catalog import CatalogError, rebuild_catalog

BACKUP_FORMAT = "openorchestrion-data-backup"
BACKUP_VERSION = 1
MANIFEST_NAME = "manifest.json"
_MAX_MANIFEST_BYTES = 8 * 1024 * 1024
_COPY_CHUNK = 1024 * 1024
_HEX = frozenset("0123456789abcdef")


class BackupError(ValueError):
    """Backup or restore input/state failed a correctness or safety check."""


@dataclass(frozen=True, slots=True)
class ManifestFile:
    path: str
    size: int
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class BackupReport:
    archive: str
    asset_count: int
    file_count: int
    history_included: bool
    bytes_archived: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RestoreReport:
    archive: str
    state_root: str
    asset_count: int
    file_count: int
    history_restored: bool
    catalog_db: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class _AssetPair:
    digest: str
    midi: Path
    sidecar: Path


@dataclass(frozen=True, slots=True)
class _Manifest:
    created_at: str
    files: tuple[ManifestFile, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": BACKUP_FORMAT,
            "version": BACKUP_VERSION,
            "created_at": self.created_at,
            "files": [entry.to_dict() for entry in self.files],
        }


def _digest_shape(value: str) -> bool:
    return len(value) == 64 and all(char in _HEX for char in value)


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while block := handle.read(_COPY_CHUNK):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


def _copy_and_hash(source: Path, destination: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as incoming, destination.open("wb") as outgoing:
        while block := incoming.read(_COPY_CHUNK):
            digest.update(block)
            size += len(block)
            outgoing.write(block)
        outgoing.flush()
        os.fsync(outgoing.fileno())
    return digest.hexdigest(), size


def _fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _fsync_parent(path: Path) -> None:
    try:
        descriptor = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError:
        # Some development/test filesystems do not support directory fsync. The
        # data file itself has already been fsynced before the atomic rename.
        pass


def _asset_pairs(library_root: Path) -> tuple[_AssetPair, ...]:
    assets = library_root / "assets"
    if not assets.is_dir():
        raise BackupError(f"asset directory does not exist: {assets}")

    midi: dict[str, Path] = {}
    sidecars: dict[str, Path] = {}
    for path in sorted(assets.iterdir()):
        if path.name.endswith(".json.lock"):
            # Metadata writer lock files are synchronization state, not durable
            # content. They are intentionally permanent and never archived.
            continue
        if path.is_symlink():
            raise BackupError(f"asset directory contains a symlink: {path}")
        if not path.is_file():
            raise BackupError(f"asset directory contains an unexpected entry: {path}")
        suffix = path.suffix.casefold()
        if suffix not in {".mid", ".json"} or not _digest_shape(path.stem):
            raise BackupError(f"asset directory contains an unexpected file: {path.name}")
        bucket = midi if suffix == ".mid" else sidecars
        bucket[path.stem] = path

    missing_sidecars = sorted(set(midi) - set(sidecars))
    missing_midi = sorted(set(sidecars) - set(midi))
    if missing_sidecars:
        raise BackupError(f"MIDI object has no sidecar: {missing_sidecars[0]}")
    if missing_midi:
        raise BackupError(f"sidecar has no MIDI object: {missing_midi[0]}")

    return tuple(
        _AssetPair(digest=digest, midi=midi[digest], sidecar=sidecars[digest])
        for digest in sorted(midi)
    )


def _validate_sidecar_bytes(payload: bytes, *, digest: str, midi_size: int) -> dict[str, Any]:
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BackupError(f"{digest}.json is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise BackupError(f"{digest}.json must contain a JSON object")
    if document.get("schema_version") != 1:
        raise BackupError(f"{digest}.json has unsupported schema_version")
    if document.get("asset_id") != f"sha256:{digest}":
        raise BackupError(f"{digest}.json asset_id does not match its content address")

    file_info = document.get("file")
    analysis = document.get("deterministic_analysis")
    if not isinstance(file_info, dict) or not isinstance(analysis, dict):
        raise BackupError(f"{digest}.json is missing file/deterministic_analysis objects")
    if file_info.get("sha256") != digest:
        raise BackupError(f"{digest}.json file.sha256 does not match its content address")
    if file_info.get("stored_filename") != f"{digest}.mid":
        raise BackupError(f"{digest}.json stored_filename does not match its content address")
    recorded_size = file_info.get("size_bytes")
    if recorded_size is not None and recorded_size != midi_size:
        raise BackupError(
            f"{digest}.json records size_bytes={recorded_size}, actual MIDI size is {midi_size}"
        )
    if analysis.get("sha256") != digest:
        raise BackupError(f"{digest}.json deterministic_analysis.sha256 does not match")
    return document


def _stage_assets(source_library: Path, staged_library: Path) -> tuple[ManifestFile, ...]:
    pairs = _asset_pairs(source_library)
    staged_assets = staged_library / "assets"
    staged_assets.mkdir(parents=True, exist_ok=True)
    entries: list[ManifestFile] = []

    for pair in pairs:
        staged_midi = staged_assets / pair.midi.name
        midi_hash, midi_size = _copy_and_hash(pair.midi, staged_midi)
        if midi_hash != pair.digest:
            raise BackupError(
                f"stored MIDI object {pair.midi.name} hashes to {midi_hash}; library is corrupt"
            )

        # Sidecar replacement is atomic in the metadata writer, so one read is
        # always a complete old or new document, never a torn edit.
        sidecar_bytes = pair.sidecar.read_bytes()
        _validate_sidecar_bytes(sidecar_bytes, digest=pair.digest, midi_size=midi_size)
        staged_sidecar = staged_assets / pair.sidecar.name
        staged_sidecar.write_bytes(sidecar_bytes)
        _fsync_file(staged_sidecar)

        sidecar_hash = hashlib.sha256(sidecar_bytes).hexdigest()
        entries.extend(
            (
                ManifestFile(
                    path=f"library/assets/{pair.midi.name}",
                    size=midi_size,
                    sha256=midi_hash,
                ),
                ManifestFile(
                    path=f"library/assets/{pair.sidecar.name}",
                    size=len(sidecar_bytes),
                    sha256=sidecar_hash,
                ),
            )
        )

    # Detect an import/removal that raced the inventory pass. An individual
    # sidecar edit is safe because we captured one atomic version of that file;
    # changing the set of assets means the requested library snapshot moved.
    after = tuple(pair.digest for pair in _asset_pairs(source_library))
    before = tuple(pair.digest for pair in pairs)
    if after != before:
        raise BackupError("library asset set changed during backup; retry the backup")

    # Exercise the same strict sidecar/index path a restore will depend on. The
    # generated catalog proves all staged sidecars are indexable, then is deleted
    # because catalogs are not authoritative backup data.
    try:
        rebuild_catalog(staged_library, strict=True)
    except (CatalogError, KeyError, TypeError, ValueError, OSError) as exc:
        raise BackupError(f"staged library cannot rebuild its catalog: {exc}") from exc
    (staged_library / "catalog.db").unlink(missing_ok=True)
    return tuple(sorted(entries, key=lambda entry: entry.path))


def _validate_history_db(path: Path) -> None:
    try:
        with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as conn:
            quick = conn.execute("PRAGMA quick_check").fetchone()
            if quick is None or quick[0] != "ok":
                raise BackupError(f"history database quick_check failed: {quick!r}")
            foreign = conn.execute("PRAGMA foreign_key_check").fetchone()
            if foreign is not None:
                raise BackupError(f"history database foreign-key check failed: {foreign!r}")
            row = conn.execute(
                "SELECT value FROM history_meta WHERE key='schema_version'"
            ).fetchone()
            if row is None or int(row[0]) != HISTORY_SCHEMA_VERSION:
                found = None if row is None else row[0]
                raise BackupError(
                    f"unsupported history schema version {found!r}; expected {HISTORY_SCHEMA_VERSION}"
                )
    except BackupError:
        raise
    except (sqlite3.DatabaseError, OSError, ValueError) as exc:
        raise BackupError(f"invalid history database {path}: {exc}") from exc


def _stage_history(source: Path, destination: Path) -> ManifestFile:
    if source.is_symlink() or not source.is_file():
        raise BackupError(f"history path is not a regular file: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with closing(sqlite3.connect(f"file:{source}?mode=ro", uri=True)) as incoming:
            with closing(sqlite3.connect(destination)) as outgoing:
                incoming.backup(outgoing)
                outgoing.commit()
    except sqlite3.DatabaseError as exc:
        destination.unlink(missing_ok=True)
        raise BackupError(f"could not snapshot history database: {exc}") from exc
    _validate_history_db(destination)
    digest, size = _sha256_file(destination)
    return ManifestFile(path="history.db", size=size, sha256=digest)


def _manifest_bytes(manifest: _Manifest) -> bytes:
    return (json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n").encode("utf-8")


def _write_archive(staging: Path, destination: Path, manifest: _Manifest) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(
            temporary,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
        ) as archive:
            archive.writestr(MANIFEST_NAME, _manifest_bytes(manifest))
            for entry in manifest.files:
                archive.write(staging / Path(entry.path), arcname=entry.path)
        _fsync_file(temporary)
        os.replace(temporary, destination)
        _fsync_parent(destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def create_backup(state_root: str | Path, destination: str | Path) -> BackupReport:
    """Create one verified, atomically-published application-data backup archive."""
    root = Path(state_root).resolve()
    archive = Path(destination).resolve()
    if not root.is_dir():
        raise BackupError(f"state root does not exist: {root}")
    if archive.exists() and archive.is_dir():
        raise BackupError(f"backup destination is a directory: {archive}")

    with tempfile.TemporaryDirectory(prefix="openorchestrion-backup-") as temp_name:
        staging = Path(temp_name)
        files = list(_stage_assets(root / "library", staging / "library"))
        history_included = False
        history = root / "history.db"
        if history.exists():
            files.append(_stage_history(history, staging / "history.db"))
            history_included = True
        manifest = _Manifest(
            created_at=datetime.now(UTC).isoformat(),
            files=tuple(sorted(files, key=lambda entry: entry.path)),
        )
        _write_archive(staging, archive, manifest)

    return BackupReport(
        archive=str(archive),
        asset_count=sum(1 for entry in manifest.files if entry.path.endswith(".mid")),
        file_count=len(manifest.files),
        history_included=history_included,
        bytes_archived=sum(entry.size for entry in manifest.files),
    )


def _zip_member_kind(info: zipfile.ZipInfo) -> int:
    return stat.S_IFMT((info.external_attr >> 16) & 0xFFFF)


def _safe_member_name(name: str) -> str:
    if not name or "\\" in name or "\x00" in name:
        raise BackupError(f"unsafe archive member path: {name!r}")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise BackupError(f"unsafe archive member path: {name!r}")
    normalized = str(path)
    if normalized != name or name.endswith("/"):
        raise BackupError(f"non-canonical archive member path: {name!r}")
    return normalized


def _allowed_payload_path(path: str) -> bool:
    if path == "history.db":
        return True
    pure = PurePosixPath(path)
    if len(pure.parts) != 3 or pure.parts[:2] != ("library", "assets"):
        return False
    leaf = pure.name
    suffix = PurePosixPath(leaf).suffix.casefold()
    stem = leaf[: -len(suffix)] if suffix else leaf
    return suffix in {".mid", ".json"} and _digest_shape(stem)


def _read_manifest(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> _Manifest:
    if info.file_size > _MAX_MANIFEST_BYTES:
        raise BackupError("backup manifest is unreasonably large")
    try:
        document = json.loads(archive.read(info).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RuntimeError) as exc:
        raise BackupError(f"backup manifest is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise BackupError("backup manifest must be a JSON object")
    if document.get("format") != BACKUP_FORMAT:
        raise BackupError(f"unexpected backup format: {document.get('format')!r}")
    if document.get("version") != BACKUP_VERSION:
        raise BackupError(
            f"unsupported backup version {document.get('version')!r}; expected {BACKUP_VERSION}"
        )
    created_at = document.get("created_at")
    if not isinstance(created_at, str) or not created_at.strip():
        raise BackupError("backup manifest created_at must be a non-empty string")
    raw_files = document.get("files")
    if not isinstance(raw_files, list):
        raise BackupError("backup manifest files must be an array")

    files: list[ManifestFile] = []
    seen: set[str] = set()
    for raw in raw_files:
        if not isinstance(raw, dict) or set(raw) != {"path", "size", "sha256"}:
            raise BackupError("backup manifest file entries must contain path, size, sha256 only")
        path = raw.get("path")
        size = raw.get("size")
        digest = raw.get("sha256")
        if not isinstance(path, str):
            raise BackupError("backup manifest path must be a string")
        path = _safe_member_name(path)
        if not _allowed_payload_path(path):
            raise BackupError(f"backup manifest contains an unexpected path: {path}")
        if path in seen:
            raise BackupError(f"backup manifest contains duplicate path: {path}")
        seen.add(path)
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise BackupError(f"backup manifest has invalid size for {path}")
        if not isinstance(digest, str) or not _digest_shape(digest):
            raise BackupError(f"backup manifest has invalid SHA-256 for {path}")
        files.append(ManifestFile(path=path, size=size, sha256=digest))
    return _Manifest(created_at=created_at, files=tuple(files))


def _inspect_archive(archive: zipfile.ZipFile) -> tuple[_Manifest, dict[str, zipfile.ZipInfo]]:
    members: dict[str, zipfile.ZipInfo] = {}
    for info in archive.infolist():
        name = _safe_member_name(info.filename)
        if name in members:
            raise BackupError(f"backup archive contains duplicate member: {name}")
        kind = _zip_member_kind(info)
        if info.is_dir() or kind == stat.S_IFLNK:
            raise BackupError(f"backup archive contains a non-regular member: {name}")
        if kind not in {0, stat.S_IFREG}:
            raise BackupError(f"backup archive contains unsupported member type: {name}")
        members[name] = info

    manifest_info = members.get(MANIFEST_NAME)
    if manifest_info is None:
        raise BackupError("backup archive has no manifest.json")
    manifest = _read_manifest(archive, manifest_info)
    expected = {MANIFEST_NAME, *(entry.path for entry in manifest.files)}
    actual = set(members)
    if actual != expected:
        extra = sorted(actual - expected)
        missing = sorted(expected - actual)
        detail = []
        if extra:
            detail.append(f"unexpected={extra[:3]}")
        if missing:
            detail.append(f"missing={missing[:3]}")
        raise BackupError("backup members do not match manifest: " + ", ".join(detail))
    for entry in manifest.files:
        if members[entry.path].file_size != entry.size:
            raise BackupError(f"archive size for {entry.path} does not match manifest")
    return manifest, members


def _stream_member(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    destination: Path,
    expected: ManifestFile,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    try:
        with archive.open(info, "r") as incoming, destination.open("wb") as outgoing:
            while block := incoming.read(_COPY_CHUNK):
                digest.update(block)
                size += len(block)
                if size > expected.size:
                    raise BackupError(f"archive member {expected.path} exceeds its declared size")
                outgoing.write(block)
            outgoing.flush()
            os.fsync(outgoing.fileno())
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    if size != expected.size or digest.hexdigest() != expected.sha256:
        destination.unlink(missing_ok=True)
        raise BackupError(f"archive member {expected.path} failed size/SHA-256 verification")


def _validate_staged_library(library_root: Path) -> int:
    pairs = _asset_pairs(library_root)
    for pair in pairs:
        midi_hash, midi_size = _sha256_file(pair.midi)
        if midi_hash != pair.digest:
            raise BackupError(
                f"restored MIDI object {pair.midi.name} hashes to {midi_hash}, expected {pair.digest}"
            )
        _validate_sidecar_bytes(pair.sidecar.read_bytes(), digest=pair.digest, midi_size=midi_size)
    try:
        rebuild_catalog(library_root, strict=True)
    except (CatalogError, KeyError, TypeError, ValueError, OSError) as exc:
        raise BackupError(f"restored library cannot rebuild its catalog: {exc}") from exc
    return len(pairs)


def _target_is_available(target: Path) -> bool:
    if target.is_symlink():
        return False
    if not target.exists():
        return True
    if not target.is_dir():
        return False
    try:
        next(target.iterdir())
    except StopIteration:
        return True
    return False


def restore_backup(archive_path: str | Path, state_root: str | Path) -> RestoreReport:
    """Verify an entire backup and atomically publish it as a blank state root."""
    source = Path(archive_path).resolve()
    target = Path(state_root).resolve()
    if source.is_symlink() or not source.is_file():
        raise BackupError(f"backup archive is not a regular file: {source}")
    if not _target_is_available(target):
        raise BackupError(f"restore target must be absent or empty: {target}")

    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{target.name}.restore.{uuid4().hex}.", dir=target.parent)
    )
    published = False
    try:
        try:
            with zipfile.ZipFile(source, "r") as archive:
                manifest, members = _inspect_archive(archive)
                for entry in manifest.files:
                    _stream_member(
                        archive,
                        members[entry.path],
                        staging / Path(entry.path),
                        entry,
                    )
        except zipfile.BadZipFile as exc:
            raise BackupError(f"not a valid OpenOrchestrion backup ZIP: {exc}") from exc

        library = staging / "library"
        (library / "assets").mkdir(parents=True, exist_ok=True)
        asset_count = _validate_staged_library(library)
        history_restored = (staging / "history.db").is_file()
        if history_restored:
            _validate_history_db(staging / "history.db")

        # Recheck immediately before publication so another process cannot fill
        # an initially-empty target while a large archive is being verified.
        if not _target_is_available(target):
            raise BackupError(f"restore target changed while restore was being verified: {target}")
        if target.exists():
            target.rmdir()
        os.replace(staging, target)
        published = True
        _fsync_parent(target)
    finally:
        if not published:
            shutil.rmtree(staging, ignore_errors=True)

    return RestoreReport(
        archive=str(source),
        state_root=str(target),
        asset_count=asset_count,
        file_count=len(manifest.files),
        history_restored=history_restored,
        catalog_db=str(target / "library" / "catalog.db"),
    )


__all__ = [
    "BACKUP_FORMAT",
    "BACKUP_VERSION",
    "BackupError",
    "BackupReport",
    "ManifestFile",
    "RestoreReport",
    "create_backup",
    "restore_backup",
]
