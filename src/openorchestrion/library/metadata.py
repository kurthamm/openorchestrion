"""Curated descriptive metadata editing.

The sidecar beside each stored MIDI object is the durable source of truth;
``catalog.db`` is a rebuildable index that may be deleted at any time. Every
edit therefore lands in the sidecar first, atomically, and the catalog is
reconciled afterwards.

Three data classes share the sidecar and must not bleed into each other:

* ``deterministic_analysis`` — facts derived from the MIDI bytes.
* ``provenance`` — where the file came from and what rights apply.
* ``descriptive_metadata`` — the curated, human-editable fields handled here.

This module writes only the third. Rights cannot be upgraded by a title or
favorite edit, and AI enrichment stays in its own block.

Validation is performed in code rather than against ``schemas/midi-asset.schema.json``
at runtime: that file lives outside the installed package, so loading it would
work from a checkout and fail from a wheel. ``tests/test_metadata_writer.py``
asserts this module and the JSON Schema agree, so the two cannot drift.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping
from uuid import uuid4

try:  # POSIX advisory locking; the appliance targets Raspberry Pi OS/Linux.
    import fcntl
except ImportError:  # pragma: no cover - Windows development only
    fcntl = None  # type: ignore[assignment]

LEVELS = {"low": 1, "medium": 3, "high": 5}
PERFORMANCE_TYPES = (
    "SOLO_PIANO",
    "MULTI_INSTRUMENT",
    "PIANO_DUET",
    "TWO_PIANO",
    "DUELING_PIANO",
    "DISTRIBUTED",
)
QUALITY_GRADES = ("A", "B", "C", "D")

TEXT_FIELDS = (
    "composition_id",
    "title",
    "composition_title",
    "composer",
    "artist",
    "era",
)
LIST_FIELDS = ("genres", "moods", "themes", "tags", "instrumentation")
LEVEL_FIELDS = ("familiarity", "energy")

#: Every key this module will write. Mirrors the schema's descriptive_metadata
#: block, which forbids additional properties.
CURATED_FIELDS: tuple[str, ...] = (
    *TEXT_FIELDS,
    "year_composed",
    *LIST_FIELDS,
    "performance_type",
    "quality_grade",
    *LEVEL_FIELDS,
    "favorite",
)

#: Blocks an edit may never touch, named so the error can say why.
PROTECTED_BLOCKS = ("deterministic_analysis", "provenance", "ai_enrichment", "file")


class MetadataError(ValueError):
    """Base class for every failure this module raises."""


class AssetNotFoundError(MetadataError):
    pass


class MetadataValidationError(MetadataError):
    pass


class MetadataConflictError(MetadataError):
    """Raised when the sidecar changed since the caller last read it."""

    def __init__(self, asset_id: str, expected: str, actual: str) -> None:
        super().__init__(
            f"{asset_id} was modified by someone else "
            f"(expected revision {expected[:12]}, found {actual[:12]})"
        )
        self.asset_id = asset_id
        self.expected = expected
        self.actual = actual


@dataclass(frozen=True, slots=True)
class MetadataRecord:
    """A sidecar's curated block plus the revision it was read at."""

    asset_id: str
    revision: str
    descriptive_metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "revision": self.revision,
            "descriptive_metadata": dict(self.descriptive_metadata),
        }


@dataclass(frozen=True, slots=True)
class BulkFailure:
    asset_id: str
    reason: str
    error_type: str

    def to_dict(self) -> dict[str, Any]:
        return {"asset_id": self.asset_id, "reason": self.reason, "error_type": self.error_type}


@dataclass(frozen=True, slots=True)
class BulkResult:
    """Outcome of a bulk edit: what was written, and what was refused."""

    updated: tuple[MetadataRecord, ...]
    failed: tuple[BulkFailure, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "updated": [record.to_dict() for record in self.updated],
            "failed": [failure.to_dict() for failure in self.failed],
            "counts": {"updated": len(self.updated), "failed": len(self.failed)},
        }


# ---------------------------------------------------------------- identity


def normalize_asset_id(asset_id: str) -> str:
    """Accept ``sha256:<hex>`` or a bare digest, return the canonical form.

    The catalog stores the prefixed form while sidecars are named by the bare
    digest, so callers legitimately arrive with either.
    """
    if not isinstance(asset_id, str):
        raise MetadataValidationError("asset_id must be a string")
    candidate = asset_id.strip().lower()
    if candidate.startswith("sha256:"):
        candidate = candidate[len("sha256:") :]
    if len(candidate) != 64 or any(char not in "0123456789abcdef" for char in candidate):
        raise MetadataValidationError(f"not a SHA-256 asset id: {asset_id!r}")
    return f"sha256:{candidate}"


def sidecar_path(library_root: str | Path, asset_id: str) -> Path:
    digest = normalize_asset_id(asset_id).split(":", 1)[1]
    return Path(library_root) / "assets" / f"{digest}.json"


def _revision(payload: bytes) -> str:
    """A sidecar's revision is a digest of its bytes — no extra state to keep."""
    return hashlib.sha256(payload).hexdigest()


# -------------------------------------------------------------- validation


def _text(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise MetadataValidationError(f"{name} must be a string")
    text = value.strip()
    if not text:
        raise MetadataValidationError(f"{name} must not be empty")
    return text


def _string_list(name: str, value: Any) -> list[str]:
    """Normalize free text without locking it to a vocabulary.

    A hobbyist library will always carry tags nobody anticipated, so values are
    accepted as written and only tidied: trimmed, blanks dropped, and duplicates
    that differ solely by case collapsed onto the first spelling seen.
    """
    if isinstance(value, str):
        value = [part for part in value.split(",")]
    if not isinstance(value, (list, tuple)):
        raise MetadataValidationError(f"{name} must be a string or a list of strings")
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise MetadataValidationError(f"{name} entries must be strings")
        text = item.strip()
        if not text:
            continue
        key = text.casefold()
        if key not in seen:
            seen.add(key)
            result.append(text)
    return result


def _level(name: str, value: Any) -> int:
    """Accept low/medium/high or 1..5, store the integer.

    The schema permits either spelling; normalizing on write keeps round-trips
    deterministic and matches how the catalog already indexes these.
    """
    if isinstance(value, bool):
        raise MetadataValidationError(f"{name} must be 1..5 or low/medium/high")
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in LEVELS:
            return LEVELS[lowered]
        try:
            value = int(lowered)
        except ValueError:
            raise MetadataValidationError(
                f"{name} must be 1..5 or low/medium/high, got {value!r}"
            ) from None
    if not isinstance(value, int):
        raise MetadataValidationError(f"{name} must be 1..5 or low/medium/high")
    if not 1 <= value <= 5:
        raise MetadataValidationError(f"{name} must be between 1 and 5, got {value}")
    return value


def _year(value: Any) -> int:
    if isinstance(value, bool):
        raise MetadataValidationError("year_composed must be an integer")
    if isinstance(value, str):
        try:
            value = int(value.strip())
        except ValueError:
            raise MetadataValidationError(f"year_composed must be an integer, got {value!r}") from None
    if not isinstance(value, int):
        raise MetadataValidationError("year_composed must be an integer")
    if not 1 <= value <= 9999:
        raise MetadataValidationError(f"year_composed must be between 1 and 9999, got {value}")
    return value


def _boolean(name: str, value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1", "y"}:
            return True
        if lowered in {"false", "no", "0", "n"}:
            return False
    raise MetadataValidationError(f"{name} must be true or false")


def _enum(name: str, value: Any, allowed: tuple[str, ...]) -> str:
    text = _text(name, value)
    upper = text.upper()
    if upper not in allowed:
        raise MetadataValidationError(f"{name} must be one of {', '.join(allowed)}, got {text!r}")
    return upper


def coerce_field(name: str, value: Any) -> Any:
    """Validate and normalize one curated field, or raise."""
    if name not in CURATED_FIELDS:
        if name in PROTECTED_BLOCKS:
            raise MetadataValidationError(
                f"{name} is not curated metadata and cannot be edited here"
            )
        raise MetadataValidationError(f"unknown descriptive metadata field: {name}")
    if name in TEXT_FIELDS:
        return _text(name, value)
    if name in LIST_FIELDS:
        return _string_list(name, value)
    if name in LEVEL_FIELDS:
        return _level(name, value)
    if name == "year_composed":
        return _year(value)
    if name == "favorite":
        return _boolean(name, value)
    if name == "performance_type":
        return _enum(name, value, PERFORMANCE_TYPES)
    if name == "quality_grade":
        return _enum(name, value, QUALITY_GRADES)
    raise MetadataValidationError(f"unhandled field: {name}")  # pragma: no cover


def normalize_metadata(changes: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a whole change set before anything is written.

    Every field is checked first so a bad value cannot leave a partially
    applied edit behind.
    """
    normalized: dict[str, Any] = {}
    for name, value in changes.items():
        normalized[name] = coerce_field(name, value)
    return normalized


# ------------------------------------------------------------------- I/O


@contextmanager
def _asset_write_lock(path: Path) -> Iterator[None]:
    """Serialize writers for one sidecar.

    The revision check alone is a time-of-check/time-of-use race: two processes
    can both read revision R, both find it current, and the second ``os.replace``
    then silently discards the first edit. Holding an exclusive advisory lock
    across read → check → write closes that window, so the second writer re-reads
    the *new* revision and is correctly rejected as stale.

    The lock file lives beside the sidecar and is deliberately not removed:
    unlinking it would let a waiting process acquire a lock on a file nobody
    else can see any more.
    """
    if fcntl is None:  # pragma: no cover - non-POSIX development host
        # Without advisory locking the revision check still rejects sequential
        # stale writes; only the concurrent case degrades.
        yield
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    handle = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(handle, fcntl.LOCK_UN)
        finally:
            os.close(handle)


def _load_document(path: Path, asset_id: str) -> tuple[dict[str, Any], str]:
    try:
        payload = path.read_bytes()
    except FileNotFoundError:
        raise AssetNotFoundError(f"no sidecar for {asset_id}") from None
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MetadataError(f"{path}: sidecar is not readable JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise MetadataError(f"{path}: sidecar must be a JSON object")
    return document, _revision(payload)


def read_metadata(library_root: str | Path, asset_id: str) -> MetadataRecord:
    """Read the curated block and the revision needed to safely write it back."""
    canonical = normalize_asset_id(asset_id)
    path = sidecar_path(library_root, canonical)
    document, revision = _load_document(path, canonical)
    curated = document.get("descriptive_metadata") or {}
    if not isinstance(curated, dict):
        raise MetadataError(f"{path}: descriptive_metadata must be an object")
    return MetadataRecord(asset_id=canonical, revision=revision, descriptive_metadata=curated)


def _write_atomic(path: Path, document: Mapping[str, Any]) -> str:
    """Replace the sidecar in one step so an interrupted edit cannot corrupt it.

    The temporary file is created beside the target so ``os.replace`` stays on
    one filesystem and is therefore atomic, and it is fsynced before the swap so
    a power loss cannot leave a truncated file in place.
    """
    payload = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
    # Unique per write, not merely per process: two threads sharing one temp
    # name would let the first os.replace consume the second's file. The write
    # lock prevents that today, but a foot-gun that only a lock defuses is one
    # refactor away from being live.
    temporary = path.with_name(f"{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return _revision(payload)


def update_metadata(
    library_root: str | Path,
    asset_id: str,
    changes: Mapping[str, Any] | None = None,
    *,
    remove: Iterable[str] = (),
    expected_revision: str | None = None,
) -> MetadataRecord:
    """Apply curated edits to one sidecar and return the new record.

    ``expected_revision`` is optimistic concurrency: pass the revision the edit
    was based on and the write is refused if the sidecar moved underneath it,
    so two editors cannot silently overwrite one another. Omit it to force.

    Nothing is written unless every field validates, so an invalid edit always
    leaves the previous valid sidecar in place.
    """
    canonical = normalize_asset_id(asset_id)
    path = sidecar_path(library_root, canonical)

    removals = tuple(remove)
    for name in removals:
        if name not in CURATED_FIELDS:
            raise MetadataValidationError(f"cannot remove unknown field: {name}")

    # Validate the entire change set before touching the document, and before
    # taking the lock: a malformed edit should not make other writers wait.
    normalized = normalize_metadata(changes or {})

    with _asset_write_lock(path):
        document, revision = _load_document(path, canonical)
        if expected_revision is not None and expected_revision != revision:
            raise MetadataConflictError(canonical, expected_revision, revision)

        curated = dict(document.get("descriptive_metadata") or {})
        curated.update(normalized)
        for name in removals:
            curated.pop(name, None)
        # An empty list carries no information and would otherwise linger.
        for name in LIST_FIELDS:
            if name in curated and not curated[name]:
                curated.pop(name)

        document["descriptive_metadata"] = curated
        new_revision = _write_atomic(path, document)

    return MetadataRecord(
        asset_id=canonical,
        revision=new_revision,
        descriptive_metadata=curated,
    )


def set_favorite(
    library_root: str | Path,
    asset_id: str,
    favorite: bool,
    *,
    expected_revision: str | None = None,
) -> MetadataRecord:
    """Persist a favorite toggle. The narrow case the appliance UI needs."""
    return update_metadata(
        library_root,
        asset_id,
        {"favorite": bool(favorite)},
        expected_revision=expected_revision,
    )


# --------------------------------------------------------- re-analysis


def midi_path(library_root: str | Path, asset_id: str) -> Path:
    digest = normalize_asset_id(asset_id).split(":", 1)[1]
    return Path(library_root) / "assets" / f"{digest}.mid"


def reanalyze_asset(
    library_root: str | Path,
    asset_id: str,
    *,
    expected_revision: str | None = None,
) -> MetadataRecord:
    """Recompute ``deterministic_analysis`` from the stored MIDI bytes.

    Deterministic facts are derived, so a corrected analyzer makes every
    existing sidecar stale. This is how a library is repaired in place: rerun
    the analyzer over the immutable stored object and replace only that block,
    leaving curated metadata, provenance and AI enrichment untouched.

    Issue #21 uses this to repair ``peak_simultaneous_notes`` after correcting
    how sustained notes are counted.

    The stored object is content-addressed, so its digest must still match the
    asset id; a mismatch means library corruption and is refused rather than
    written over.
    """
    from ..midi.analyzer import analyze_midi  # local: avoids a cycle at import

    canonical = normalize_asset_id(asset_id)
    path = sidecar_path(library_root, canonical)
    source = midi_path(library_root, canonical)
    if not source.is_file():
        raise AssetNotFoundError(f"no stored MIDI object for {canonical}")

    analysis = analyze_midi(source)
    digest = analysis.sha256
    if digest is None or f"sha256:{digest}" != canonical:
        raise MetadataError(
            f"{canonical}: stored object hashes to {digest}; refusing to rewrite analysis"
        )

    document_analysis = analysis.to_dict()
    # Never persist this machine's absolute path in durable metadata.
    document_analysis["source"] = source.name

    with _asset_write_lock(path):
        document, revision = _load_document(path, canonical)
        if expected_revision is not None and expected_revision != revision:
            raise MetadataConflictError(canonical, expected_revision, revision)
        document["deterministic_analysis"] = document_analysis
        new_revision = _write_atomic(path, document)

    curated = document.get("descriptive_metadata") or {}
    return MetadataRecord(
        asset_id=canonical,
        revision=new_revision,
        descriptive_metadata=curated,
    )


def reanalyze_library(library_root: str | Path) -> BulkResult:
    """Re-analyze every stored asset, isolating failures to the asset at fault.

    A repair sweep over a large collection must not stop at the first
    unreadable object.
    """
    assets = Path(library_root) / "assets"
    updated: list[MetadataRecord] = []
    failed: list[BulkFailure] = []
    for sidecar in sorted(assets.glob("*.json")):
        asset_id = f"sha256:{sidecar.stem}"
        try:
            updated.append(reanalyze_asset(library_root, asset_id))
        except MetadataError as exc:
            failed.append(
                BulkFailure(asset_id=asset_id, reason=str(exc), error_type=type(exc).__name__)
            )
        except Exception as exc:  # noqa: BLE001 - one unreadable object, not a sweep
            failed.append(
                BulkFailure(
                    asset_id=asset_id,
                    reason=str(exc) or type(exc).__name__,
                    error_type=type(exc).__name__,
                )
            )
    return BulkResult(updated=tuple(updated), failed=tuple(failed))


# ------------------------------------------------------------------ bulk


def read_csv_edits(csv_path: str | Path) -> list[tuple[str, dict[str, Any]]]:
    """Parse a bulk edit file keyed by SHA-256.

    One row per asset; columns are curated field names. Blank cells are left
    alone rather than cleared, so a spreadsheet exported with every column does
    not wipe fields the editor never filled in.
    """
    path = Path(csv_path)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise MetadataValidationError(f"{path}: file has no header row")
        key = next(
            (name for name in reader.fieldnames if name.strip().lower() in {"asset_id", "sha256"}),
            None,
        )
        if key is None:
            raise MetadataValidationError(f"{path}: needs an asset_id or sha256 column")

        edits: list[tuple[str, dict[str, Any]]] = []
        for number, row in enumerate(reader, start=2):
            identifier = (row.get(key) or "").strip()
            if not identifier:
                continue
            changes = {
                name.strip(): value
                for name, value in row.items()
                if name and name != key and value is not None and str(value).strip()
            }
            if not changes:
                continue
            unknown = sorted(set(changes) - set(CURATED_FIELDS))
            if unknown:
                raise MetadataValidationError(
                    f"{path}: row {number} has unknown column(s): {', '.join(unknown)}"
                )
            edits.append((identifier, changes))
    return edits


def apply_edits(
    library_root: str | Path,
    edits: Iterable[tuple[str, Mapping[str, Any]]],
) -> BulkResult:
    """Apply many edits, isolating failures to the asset that caused them."""
    updated: list[MetadataRecord] = []
    failed: list[BulkFailure] = []
    for asset_id, changes in edits:
        try:
            updated.append(update_metadata(library_root, asset_id, changes))
        except MetadataError as exc:
            failed.append(
                BulkFailure(asset_id=str(asset_id), reason=str(exc), error_type=type(exc).__name__)
            )
    return BulkResult(updated=tuple(updated), failed=tuple(failed))
