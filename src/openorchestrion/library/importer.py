from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from openorchestrion.midi.analyzer import MidiAnalysis, analyze_midi

from .rights import (
    COMPOSITION_RIGHTS,
    EVIDENCE_FIELDS,
    ESTABLISHED_LICENSES,
    REDISTRIBUTION,
    RIGHTS_STATUSES,
    RightsError,
    RightsEvidence,
    normalize,
    verify,
)

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
    rights: RightsEvidence,
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
            **rights.to_dict(),
        },
        "deterministic_analysis": analysis_document,
        "descriptive_metadata": {},
        "ai_enrichment": [],
    }


def _file_digest(path: Path) -> str:
    """SHA-256 of a file, read in chunks so a large import stays bounded."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(_COMPARE_CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


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
    rights: RightsEvidence | None = None,
    max_bytes: int | None = DEFAULT_MAX_BYTES,
) -> ImportResult:
    """Copy one MIDI file into the content-addressed library.

    ``rights`` records where the file came from and what may be done with it.
    A ``verified-open`` claim is audited before anything is written, so an
    unsupported claim fails the import rather than becoming a durable assertion
    that later readers have no way to distinguish from a researched one.
    """
    _validate_max_bytes(max_bytes)
    evidence = rights if rights is not None else RightsEvidence(rights_status="personal")
    verify(evidence)
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
            rights=evidence,
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


# --------------------------------------------------------- curation manifest


class ManifestError(ValueError):
    """Raised when a curation manifest cannot be read at all."""


@dataclass(frozen=True, slots=True)
class CurationEntry:
    """One researched candidate: a file, and the evidence gathered about it."""

    path: str
    rights: RightsEvidence
    expected_sha256: str | None = None
    row: int = 0
    error: str | None = None
    """A problem with this row alone, carried rather than raised.

    A malformed cell is one curator's typo, not a broken manifest. Raising
    would cost every other row in the file, including the thirty-nine that
    were fine, which is the opposite of what a curation run needs.
    """


def read_curation_manifest(csv_path: str | Path) -> list[CurationEntry]:
    """Parse a curation manifest: one row per file, columns are evidence fields.

    A starter catalog is not one rights claim applied to a folder. Every file
    has its own source, its own license and its own composer, so evidence has to
    arrive per file or it is not evidence at all — it is a guess averaged over a
    directory.

    ``path`` names the file. An optional ``sha256`` column records the digest of
    the file whose terms were actually read, which is what makes the research
    transferable: the person who verified the license and the machine that
    imports the bytes are usually not the same, and without the digest there is
    nothing tying the claim to any particular sequence of bytes.

    Blank cells are omitted rather than written, so a spreadsheet exported with
    every column does not stamp empty strings over fields nobody filled in.
    """
    path = Path(csv_path)
    try:
        handle = path.open("r", encoding="utf-8-sig", newline="")
    except OSError as exc:
        raise ManifestError(f"{path}: cannot be read ({exc})") from None

    with handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ManifestError(f"{path}: file has no header row")

        columns = {name.strip() for name in reader.fieldnames if name}
        if "path" not in columns:
            raise ManifestError(f"{path}: needs a 'path' column naming each file")
        unknown = sorted(columns - {"path", "sha256"} - set(EVIDENCE_FIELDS))
        if unknown:
            raise ManifestError(
                f"{path}: unknown column(s): {', '.join(unknown)}. "
                f"Evidence columns are: {', '.join(EVIDENCE_FIELDS)}"
            )

        entries: list[CurationEntry] = []
        for number, row in enumerate(reader, start=2):
            cells = {
                (name or "").strip(): (value or "").strip()
                for name, value in row.items()
                if name
            }
            source = cells.get("path", "")
            if not source:
                continue

            values = {
                name: value
                for name, value in cells.items()
                if name in EVIDENCE_FIELDS and value
            }
            error: str | None = None
            try:
                evidence = RightsEvidence(**normalize(values))
            except RightsError as exc:
                # Scoped to the row. ManifestError stays for problems that make
                # the whole file unusable — no header, a misspelled column —
                # where continuing would mean guessing at every row alike.
                evidence, error = RightsEvidence(), str(exc)

            digest = cells.get("sha256") or None
            entries.append(
                CurationEntry(
                    path=source,
                    rights=evidence,
                    expected_sha256=digest.lower() if digest else None,
                    row=number,
                    error=error,
                )
            )
    return entries


def import_manifest(
    entries: Iterable[CurationEntry],
    library_root: str | Path,
    *,
    base_dir: str | Path | None = None,
    max_bytes: int | None = DEFAULT_MAX_BYTES,
) -> ImportReport:
    """Import each researched candidate under its own evidence.

    Failures are per entry and reported as data. A curation run is exactly the
    situation where aborting on the first bad row is wrong: the rest of the
    research is still good, and re-running after a fix must not re-litigate the
    files that already landed. Content addressing makes that safe — importing a
    file twice resolves to the same asset.
    """
    _validate_max_bytes(max_bytes)
    root = Path(base_dir) if base_dir is not None else Path()
    imported: list[ImportResult] = []
    failed: list[ImportFailure] = []

    for entry in entries:
        if entry.error is not None:
            failed.append(
                ImportFailure(
                    source=f"row {entry.row}: {entry.path}",
                    reason=entry.error,
                    error_type="RightsError",
                )
            )
            continue

        source = Path(entry.path)
        if not source.is_absolute():
            source = root / source
        try:
            if not source.exists():
                # The commonest curation mistake is a manifest that sits beside
                # the directory of files rather than inside it, which silently
                # resolves every row one level too high. A bare "no such file"
                # sends the curator hunting for a missing download instead.
                raise FileNotFoundError(
                    f"{source} does not exist. Manifest paths resolve against "
                    f"{root if str(root) else '.'}; put the manifest beside the "
                    f"files, include the directory in the path column, or pass "
                    f"--manifest-base"
                )
            if entry.expected_sha256 is not None:
                # Before hashing, not after. The size limit exists because these
                # archives are full of mis-named files, and a multi-gigabyte one
                # would otherwise be read end to end only to be rejected on the
                # next line for being too large.
                size = source.stat().st_size
                if max_bytes is not None and size > max_bytes:
                    raise ValueError(
                        f"file is {size} bytes, above the {max_bytes} byte import limit"
                    )
                actual = _file_digest(source)
                if actual != entry.expected_sha256:
                    # The claim was researched against specific bytes. Different
                    # bytes may be a different arrangement under different terms,
                    # so this is a rights failure, not a checksum nicety.
                    raise ValueError(
                        f"file does not match the researched digest "
                        f"(manifest {entry.expected_sha256[:12]}, file {actual[:12]}): "
                        "the evidence was gathered about a different file"
                    )
            imported.append(
                import_midi(source, library_root, rights=entry.rights, max_bytes=max_bytes)
            )
        except Exception as exc:  # noqa: BLE001 - one bad row is not the whole run
            failed.append(
                ImportFailure(
                    source=f"row {entry.row}: {entry.path}",
                    reason=_describe(exc),
                    error_type=type(exc).__name__,
                )
            )

    return ImportReport(imported=tuple(imported), failed=tuple(failed))


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
    rights: RightsEvidence | None = None,
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

    ``rights`` applies to every file in the run and is audited once, up front:
    an unsupported ``verified-open`` claim is a mistake about the run, not about
    any one file, so it raises here rather than arriving as an identical failure
    repeated once per file.
    """
    _validate_max_bytes(max_bytes)
    evidence = rights if rights is not None else RightsEvidence(rights_status="personal")
    verify(evidence)
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
                    rights=evidence,
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
    parser.add_argument(
        "sources", nargs="*", help="MIDI file(s) or directories (omit when using --from-csv)"
    )
    parser.add_argument(
        "--from-csv",
        help=(
            "Curation manifest: one row per file with its own evidence. Use this "
            "for a curated set, where every file has a different source, license "
            "and composer. Columns: path, sha256 (optional), plus evidence fields."
        ),
    )
    parser.add_argument(
        "--manifest-base",
        help="Directory that relative manifest paths are resolved against "
        "(default: alongside the manifest)",
    )
    parser.add_argument(
        "--library-root",
        default="var/library",
        help="Library root (default: var/library)",
    )
    parser.add_argument(
        "--rights-status",
        choices=RIGHTS_STATUSES,
        default="personal",
    )
    parser.add_argument(
        "--source-reference",
        help="Where this file came from: a URL or citation someone can re-check",
    )
    parser.add_argument("--source-label", help="Human-readable source name, e.g. 'Mutopia Project'")
    parser.add_argument(
        "--license",
        dest="license_name",
        help=(
            "License of the MIDI file/arrangement itself, which is a separate work "
            f"from the composition. Established ids: {', '.join(ESTABLISHED_LICENSES)}"
        ),
    )
    parser.add_argument("--license-url", help="Where the license terms were read")
    parser.add_argument("--attribution", help="Credit text this license obliges us to display")
    parser.add_argument(
        "--composition-rights",
        choices=COMPOSITION_RIGHTS,
        default="unknown",
        help="Rights in the underlying musical work, independent of this file",
    )
    parser.add_argument(
        "--composition-rights-basis",
        help="Why the composition is clear, e.g. 'composer died 1917, published 1899'",
    )
    parser.add_argument(
        "--redistribution",
        choices=REDISTRIBUTION,
        default="unknown",
        help="Whether this file may be redistributed",
    )
    parser.add_argument("--verified-by", help="Who established these terms")
    parser.add_argument("--verified-at", help="When these terms were established (ISO 8601)")
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

    if args.from_csv and args.sources:
        parser.error("give sources or --from-csv, not both")
    if not args.from_csv and not args.sources:
        parser.error("give at least one source, or --from-csv")

    try:
        report = _run_import(args)
    except (RightsError, ManifestError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from None

    _report_import(report, as_json=args.json)

    # Non-zero exit so a scripted import surfaces partial failure rather than
    # looking successful because most of the collection happened to parse.
    if report.failed:
        raise SystemExit(1)


def _run_import(args: argparse.Namespace) -> ImportReport:
    if args.from_csv:
        entries = read_curation_manifest(args.from_csv)
        base = args.manifest_base or Path(args.from_csv).parent
        return import_manifest(
            entries, args.library_root, base_dir=base, max_bytes=args.max_bytes
        )

    return import_paths(
        args.sources,
        args.library_root,
        recursive=not args.no_recursive,
        rights=RightsEvidence(
            rights_status=args.rights_status,
            source_reference=args.source_reference,
            source_label=args.source_label,
            license=args.license_name,
            license_url=args.license_url,
            attribution=args.attribution,
            composition_rights=args.composition_rights,
            composition_rights_basis=args.composition_rights_basis,
            redistribution=args.redistribution,
            verified_at=args.verified_at,
            verified_by=args.verified_by,
        ),
        max_bytes=args.max_bytes,
        fail_fast=args.fail_fast,
    )


def _report_import(report: ImportReport, *, as_json: bool) -> None:
    if as_json:
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


if __name__ == "__main__":
    main()
