"""Bounded subprocess for untrusted MIDI decoding and v2 qualification."""

import hashlib
import json
import re
from pathlib import Path
import sys

from .importer import import_midi
from .title_identity import source_identity
from .rights import RightsEvidence
from .quality import VERSION, inspect, decide
from .quality_structure import structure, infer


def assess(directory: Path, candidate: dict) -> dict:
    result = import_midi(
        directory / "download.mid",
        directory / "staged",
        rights=RightsEvidence(
            rights_status="personal",
            source_label=candidate["label"],
            source_reference=candidate["reference"],
            license=candidate.get("license", "unknown"),
            license_url=candidate.get("license_url") or None,
            attribution=candidate.get("attribution")
            or candidate["label"] + " — " + candidate["title"],
        ),
        max_bytes=2 * 1024 * 1024,
    )
    sidecar = Path(result.metadata_path)
    doc = json.loads(sidecar.read_bytes())
    doc["descriptive_metadata"].update(
        **source_identity(candidate["title"], source=candidate["label"]),
        genres=[candidate["genre"]] if candidate["genre"] else []
    )
    sidecar.write_text(json.dumps(doc), encoding="utf-8")
    record = inspect(str(sidecar))
    if record.get("error"):
        raise ValueError(record["error"])
    raw = sidecar.with_suffix(".mid").read_bytes()
    measured = structure(raw)
    proof = infer(record, measured)
    # This proof comes from a captured v2 publisher listing and its exact MIDI link,
    # not from a source-name shortcut or a score/audio transcription assumption.
    if candidate.get("publisher_capture"):
        proof = candidate["publisher_capture"] | {
            "download_sha256": hashlib.sha256(raw).hexdigest()
        }
    context = " ".join(str(candidate.get(k, "")) for k in ("title", "url"))
    if re.search(
        r"(?i)\b(backing[ _-]*tracks?|melody[ _-]*only|excerpt|snippet|demo|unfinished|incomplete|practice[ _-]*loop)\b",
        context.replace("_", " "),
    ):
        proof = {
            "completeness": "partial",
            "basis": "Publisher label identifies incomplete or accompaniment-only material",
            "source": candidate["reference"],
        }
    decision = decide(record, {record["asset_id"]: proof} if proof else {})
    if decision["status"] == "qualified":
        piano = proof.get("arrangement") == "solo_piano"
        doc["descriptive_metadata"]["performance_type"] = (
            "SOLO_PIANO" if piano else "MULTI_INSTRUMENT"
        )
        sidecar.write_text(json.dumps(doc), encoding="utf-8")
    record["sidecar_sha256"] = hashlib.sha256(sidecar.read_bytes()).hexdigest()
    record.update(decision)
    if record["status"] == "qualified":
        f = record["facts"]
        record["display"] = {
            "version": VERSION,
            "status": "qualified",
            "verification": "structural_assessment"
            if proof.get("inference")
            else "publisher_verified",
            "completeness": "Self-contained arrangement supported by MIDI structure"
            if proof.get("inference")
            else "Published complete performance or score export",
            "basis": proof["basis"],
            "source": proof["source"],
            "warnings": decision["warnings"],
            "notes": f["notes"],
            "peak_pitched_notes": f["peak_pitched_notes"],
            "parts": [
                {
                    k: p[k]
                    for k in (
                        "channel",
                        "notes",
                        "velocity_values",
                        "controllers",
                        "pitch_bend",
                        "pressure",
                    )
                }
                for p in f["parts"]
            ],
            "limitation": "Qualified by documented source and MIDI evidence; no human audition or acoustic fidelity certification.",
        }
    record["stage"] = str(sidecar)
    return record


def main():
    # A corrupt or hostile file cannot occupy the nightly worker indefinitely.
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (384 * 1024 * 1024,) * 2)
        resource.setrlimit(resource.RLIMIT_CPU, (45, 45))
    except ImportError:
        pass  # Windows tests; parent enforces a wall-clock timeout everywhere.
    directory = Path(sys.argv[1])
    candidate = json.loads((directory / "candidate.json").read_bytes())
    try:
        result = assess(directory, candidate)
    except (ValueError, EOFError) as exc:
        raw = (directory / "download.mid").read_bytes()
        result = {
            "asset_id": "sha256:" + hashlib.sha256(raw).hexdigest(),
            "status": "excluded",
            "reasons": ["unreadable_or_unsupported"],
            "error": str(exc)[:500],
            "provenance": {"source_reference": candidate["reference"]},
        }
    (directory / "result.json").write_text(json.dumps(result), encoding="utf-8")


if __name__ == "__main__":
    main()
