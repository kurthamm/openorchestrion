from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from openorchestrion.midi.analyzer import MidiAnalysis, analyze_midi

RightsStatus = Literal["personal", "verified-open", "unknown"]
SUPPORTED_EXTENSIONS = {".mid", ".midi"}

# Public MIDI archives are full of truncated downloads and mislabeled files.
# A Standard MIDI File of a few megabytes is already enormous; anything past
# this is far more likely to be a mis-named archive than music, and parsing it
# would cost real time and memory during a large import.
DEFAULT_MAX_BYTES = 32 * 1024 * 1024
_COMPARE_CHUNK = 1024 * 1024


@dataclass(frozen=True, slots=True)
class ImportFailure:
    """One file that could not be imported, and why.

    Kept as data rather than raised, so a single bad file in a large collection
    does not cost the caller everything after it.
    """

    source: str
    reason: str
    error_type: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ImportResult:
    asset_id: str
    midi_path: str
    metadata_path: str
    created: bool
    analysis: MidiAnalysis

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["analysis"] = self.analysis.to_dict()
        return result


@dataclass(frozen=True, slots=True)
class ImportReport:
    """Outcome of an import run: what landed, and what did not."""

    imported: tuple[ImportResult, ...]
    failed: tuple[ImportFailure, ...]

    @property
    def created(self) -> tuple[ImportResult, ...]:
        return tuple(result for result in self.imported if result.created)

    def to_dict(self) -> dict[str, Any]:
        return {
            "imported": [result.to_dict() for result in self.imported],
            "failed": [failure.to_dict() for failure in self.failed],
            "counts": {
                "imported": len(self.imported),
                "created": len(self.created),
                "already_present": len(self.imported) - len(self.created),
                "failed": len(self.failed),
            },
        }


def discover_midi_files(paths: Iterable[str | Path], *, recursive: bool = True) -> list[Path]:
    discovered: set[Path] = set()
    for item in paths:
        path = Path(item)
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            discovered.add(path.resolve())
        elif path.is_dir():
            iterator = path.rglob("*") if recursive else path.glob("*")
            for candidate in iterator:
                if candidate.is_file() and candidate.suffix.lower() in SUPPORTED_EXTENSIONS:
                    discovered.add(candidate.resolve())
    return sorted(discovered)


def _sidecar_document(
    source: Path,
    stored_path: Path,
    analysis: MidiAnalysis,
    *,
    rights_status: RightsStatus,
    source_reference: str | None,
    source_label: str | None,
    license_name: str | None,
    attribution: str | None,
) -> dict[str, Any]:
    if analysis.sha256 is None:
        raise ValueError("file-backed analysis must include sha256")

    analysis_document = analysis.to_dict()
    # Do not persist the importer machine's absolute source path in durable metadata.
    analysis_document["source"] = stored_path.name

    return {
        "schema_version": 1,
        "asset_id": f"sha256:{analysis.sha256}",
        "file": {
            "original_filename": source.name,
            "stored_filename": stored_path.name,
            "sha256": analysis.sha256,
            "size_bytes": analysis.file_size_bytes,
        },
        "provenance": {
            "imported_at": datetime.now(UTC).isoformat(),
            "rights_status": rights_status,
            "source_reference": source_reference,
            "source_label": source_label,
            "license": license_name,
            "attribution": attribution,
        },
        "deterministic_analysis": analysis_document,
        "descriptive_metadata": {},
        "ai_enrichment": [],
    }


def _same_contents(left: Path, right: Path) -> bool:
    """Compare two files in chunks rather than loading both into memory."""
    if left.stat().st_size != right.stat().st_size:
        return False
    with left.open("rb") as first, right.open("rb") as second:
        while True:
            block = first.read(_COMPARE_CHUNK)
            if block != second.read(_COMPARE_CHUNK):
                return False
            if not block:
                return True


def _validate_max_bytes(max_bytes: int | None) -> None:
    if max_bytes is not None and max_bytes < 0:
        raise ValueError("max_bytes must be non-negative or None")


def import_midi(
    source: str | Path,
    library_root: str | Path,
    *,
    rights_status: RightsStatus = "personal",
    source_reference: str | None = None,
    source_label: str | None = None,
    license_name: str | None = None,
    attribution: str | None = None,
    max_bytes: int | None = DEFAULT_MAX_BYTES,
) -> ImportResult:
    _validate_max_bytes(max_bytes)
    source_path = Path(source).resolve()
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    if source_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"unsupported MIDI extension: {source_path.suffix}")
    size = source_path.stat().st_size
    if size == 0:
        raise ValueError("file is empty")
    if max_bytes is not None and size > max_bytes:
        raise ValueError(f"file is {size} bytes, above the {max_bytes} byte import limit")

    analysis = analyze_midi(source_path)
    if analysis.sha256 is None:
        raise ValueError("analysis did not produce a SHA-256")

    root = Path(library_root)
    assets = root / "assets"
    assets.mkdir(parents=True, exist_ok=True)

    asset_id = analysis.sha256
    midi_path = assets / f"{asset_id}.mid"
    metadata_path = assets / f"{asset_id}.json"
    created = not midi_path.exists()

    if created:
        shutil.copy2(source_path, midi_path)
    elif not _same_contents(midi_path, source_path):
        raise RuntimeError("SHA-256 collision or corrupted library object")

    if not metadata_path.exists():
        document = _sidecar_document(
            source_path,
            midi_path,
            analysis,
            rights_status=rights_status,
            source_reference=source_reference,
            source_label=source_label,
            license_name=license_name,
            attribution=attribution,
        )
        metadata_path.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    return ImportResult(
        asset_id=asset_id,
        midi_path=str(midi_path),
        metadata_path=str(metadata_path),
        created=created,
        analysis=analysis,
    )


def _describe(exc: Exception) -> str:
    """A reason a person can act on.

    Several parse failures — EOFError above all — carry no message at all, and
    repeating the class name twice tells the user nothing about their file.
    """
    message = str(exc).strip()
    if message:
        return message
    if isinstance(exc, EOFError):
        return "file ends before the MIDI data is complete (truncated download?)"
    if isinstance(exc, UnicodeDecodeError):
        return "track text is not valid UTF-8"
    return f"unreadable MIDI data ({type(exc).__name__})"


def _rejected_explicit_source(source: str | Path) -> ImportFailure | None:
    """Return a failure for an explicit source that discovery would otherwise hide."""
    path = Path(source)
    if not path.exists():
        return ImportFailure(
            source=str(path),
            reason="path does not exist",
            error_type="FileNotFoundError",
        )
    if path.is_file() and path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        return ImportFailure(
            source=str(path),
            reason=f"unsupported MIDI extension: {path.suffix}",
            error_type="ValueError",
        )
    if not path.is_file() and not path.is_dir():
        return ImportFailure(
            source=str(path),
            reason="path is not a regular file or directory",
            error_type="ValueError",
        )
    return None


def import_paths(
    sources: Iterable[str | Path],
    library_root: str | Path,
    *,
    recursive: bool = True,
    rights_status: RightsStatus = "personal",
    source_reference: str | None = None,
    source_label: str | None = None,
    license_name: str | None = None,
    attribution: str | None = None,
    max_bytes: int | None = DEFAULT_MAX_BYTES,
    fail_fast: bool = False,
) -> ImportReport:
    """Import every discovered file, isolating failures to the file that caused them.

    A single truncated download used to abort the whole run, and because
    discovery is sorted, everything after it was silently never imported. Each
    file is now attempted independently and failures are reported as data.

    Explicit source arguments that are missing or not MIDI files are failures,
    rather than disappearing during discovery. Empty directories remain valid
    zero-file imports.

    Pass ``fail_fast=True`` to restore stop-on-first-error for scripted runs
    that would rather not proceed on a partially bad collection.
    """
    _validate_max_bytes(max_bytes)
    source_list = tuple(sources)
    imported: list[ImportResult] = []
    failed: list[ImportFailure] = []
    discoverable: list[str | Path] = []

    for source in source_list:
        rejection = _rejected_explicit_source(source)
        if rejection is not None:
            failed.append(rejection)
            if fail_fast:
                return ImportReport(imported=(), failed=tuple(failed))
        else:
            discoverable.append(source)

    files = discover_midi_files(discoverable, recursive=recursive)
    for source in files:
        try:
            imported.append(
                import_midi(
                    source,
                    library_root,
                    rights_status=rights_status,
                    source_reference=source_reference,
                    source_label=source_label,
                    license_name=license_name,
                    attribution=attribution,
                    max_bytes=max_bytes,
                )
            )
        except Exception as exc:  # noqa: BLE001 - any parse failure is one bad file, not a run
            failed.append(
                ImportFailure(
                    source=str(source),
                    reason=_describe(exc),
                    error_type=type(exc).__name__,
                )
            )
            if fail_fast:
                break

    return ImportReport(imported=tuple(imported), failed=tuple(failed))


def _non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("--max-bytes must be non-negative")
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import MIDI files into an OpenOrchestrion content-addressed library."
    )
    parser.add_argument("sources", nargs="+", help="MIDI file(s) or directories")
    parser.add_argument(
        "--library-root",
        default="var/library",
        help="Library root (default: var/library)",
    )
    parser.add_argument(
        "--rights-status",
        choices=("personal", "verified-open", "unknown"),
        default="personal",
    )
    parser.add_argument("--source-reference")
    parser.add_argument("--source-label")
    parser.add_argument("--license", dest="license_name")
    parser.add_argument("--attribution")
    parser.add_argument("--no-recursive", action="store_true")
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop at the first unreadable file instead of importing the rest",
    )
    parser.add_argument(
        "--max-bytes",
        type=_non_negative_int,
        default=DEFAULT_MAX_BYTES,
        help=f"Skip files larger than this (default: {DEFAULT_MAX_BYTES})",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = import_paths(
        args.sources,
        args.library_root,
        recursive=not args.no_recursive,
        rights_status=args.rights_status,
        source_reference=args.source_reference,
        source_label=args.source_label,
        license_name=args.license_name,
        attribution=args.attribution,
        max_bytes=args.max_bytes,
        fail_fast=args.fail_fast,
    )

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        for result in report.imported:
            state = "imported" if result.created else "already present"
            print(
                f"{state}: {result.analysis.source} -> {result.asset_id[:12]} "
                f"({result.analysis.note_count} notes, {result.analysis.duration_seconds:.2f}s)"
            )
        for failure in report.failed:
            print(f"skipped: {failure.source} ({failure.error_type}: {failure.reason})")
        if report.failed:
            print(
                f"\n{len(report.imported)} imported, {len(report.failed)} skipped.",
                file=sys.stderr,
            )

    # Non-zero exit so a scripted import surfaces partial failure rather than
    # looking successful because most of the collection happened to parse.
    if report.failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
