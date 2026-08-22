from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal

from openorchestrion.midi.analyzer import MidiAnalysis, analyze_midi

RightsStatus = Literal["personal", "verified-open", "unknown"]
SUPPORTED_EXTENSIONS = {".mid", ".midi"}


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
            "imported_at": datetime.now(timezone.utc).isoformat(),
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


def import_midi(
    source: str | Path,
    library_root: str | Path,
    *,
    rights_status: RightsStatus = "personal",
    source_reference: str | None = None,
    source_label: str | None = None,
    license_name: str | None = None,
    attribution: str | None = None,
) -> ImportResult:
    source_path = Path(source).resolve()
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    if source_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"unsupported MIDI extension: {source_path.suffix}")

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
    elif midi_path.read_bytes() != source_path.read_bytes():
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
) -> list[ImportResult]:
    files = discover_midi_files(sources, recursive=recursive)
    return [
        import_midi(
            source,
            library_root,
            rights_status=rights_status,
            source_reference=source_reference,
            source_label=source_label,
            license_name=license_name,
            attribution=attribution,
        )
        for source in files
    ]


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
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    results = import_paths(
        args.sources,
        args.library_root,
        recursive=not args.no_recursive,
        rights_status=args.rights_status,
        source_reference=args.source_reference,
        source_label=args.source_label,
        license_name=args.license_name,
        attribution=args.attribution,
    )

    if args.json:
        print(json.dumps([result.to_dict() for result in results], indent=2, sort_keys=True))
        return

    for result in results:
        state = "imported" if result.created else "already present"
        print(
            f"{state}: {result.analysis.source} -> {result.asset_id[:12]} "
            f"({result.analysis.note_count} notes, {result.analysis.duration_seconds:.2f}s)"
        )


if __name__ == "__main__":
    main()
