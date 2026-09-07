"""Build, publish or restore a complete-listening-v2 decision manifest."""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

from .quality import VERSION, decide, inspect


def build(
    root: Path, facts_path: Path, evidence_paths: list[Path], structure_path: Path | None = None
) -> dict:
    evidence = {}
    for path in evidence_paths:
        evidence.update(json.loads(path.read_bytes()))
    structural = {}
    if structure_path:
        for line in structure_path.open(encoding="utf-8"):
            measured = json.loads(line)
            structural[measured["asset_id"]] = measured
            # Never override contradictory publisher evidence of an individual part.
            existing = evidence.get(measured["asset_id"])
            if measured["inference"] and (
                not existing or existing.get("completeness") == "unresolved"
            ):
                evidence[measured["asset_id"]] = measured["inference"]
    # Older research snapshots may have broad part-name hints. Require both a
    # multi-file publisher bundle and a single sounding channel for a part verdict.
    for proof in evidence.values():
        if proof.get("completeness") == "partial" and (
            proof.get("bundle_midi_count", 0) < 2 or proof.get("sounding_channels") != 1
        ):
            proof["completeness"] = "unresolved"
    entries = []
    seen = {}
    source_counts = defaultdict(Counter)
    for line in facts_path.open(encoding="utf-8"):
        record = json.loads(line)
        if record.get("error"):
            refreshed = inspect(str(root / record["original_location"]))
            refreshed["original_location"] = record["original_location"]
            record = refreshed
        decision = decide(record, evidence)
        measured = structural.get(record["asset_id"], {}).get("structure", {})
        if decision["status"] == "qualified" and measured.get("error"):
            decision.update(status="unresolved", reasons=["structural_inspection_failed"])
        if decision["status"] == "qualified":
            fingerprint = record["facts"]["fingerprint"]
            if fingerprint in seen:
                decision.update(status="excluded", reasons=["duplicate_timed_playback"])
                decision["retained_asset_id"] = seen[fingerprint]
            else:
                seen[fingerprint] = record["asset_id"]
        entry = {k: record[k] for k in ("asset_id", "sidecar_sha256", "original_location", "title")}
        entry.update(decision)
        entry["source"] = record.get("provenance", {}).get("source_label")
        entry["facts_sha256"] = hashlib.sha256(
            json.dumps(record.get("facts"), sort_keys=True).encode()
        ).hexdigest()
        if decision["status"] == "qualified":
            proof = decision["evidence"][0]
            f = record["facts"]
            entry["display"] = {
                "version": VERSION,
                "status": "qualified",
                "completeness": "Self-contained arrangement supported by MIDI structure"
                if proof.get("inference")
                else "Published complete performance or score export",
                "verification": "structural_assessment"
                if proof.get("inference")
                else "publisher_verified",
                "basis": proof["basis"],
                "source": proof["source"],
                "warnings": decision["warnings"],
                "notes": f["notes"],
                "peak_pitched_notes": f["peak_pitched_notes"],
                "parts": [
                    {
                        "channel": p["channel"],
                        "notes": p["notes"],
                        "velocity_values": p["velocity_values"],
                        "controllers": p["controllers"],
                        "pitch_bend": p["pitch_bend"],
                        "pressure": p["pressure"],
                    }
                    for p in f["parts"]
                ],
                "limitation": "Qualified by documented source and MIDI evidence; no human audition or acoustic fidelity certification.",
            }
        source_counts[entry["source"]][entry["status"]] += 1
        entries.append(entry)
    identities = {e["asset_id"] for e in entries}
    if len(identities) != len(entries):
        raise ValueError("duplicate facts identity")
    expected = {p.relative_to(root).as_posix() for p in root.glob("assets/*.json")} | {
        p.relative_to(root).as_posix() for p in root.glob("archive/*/assets/*.json")
    }
    if {e["original_location"] for e in entries} != expected:
        raise ValueError("facts inventory is incomplete")
    return {
        "policy_version": VERSION,
        "facts_file_sha256": hashlib.sha256(facts_path.read_bytes()).hexdigest(),
        "structure_file_sha256": hashlib.sha256(structure_path.read_bytes()).hexdigest()
        if structure_path
        else None,
        "evidence_file_sha256": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in evidence_paths
        },
        "entries": entries,
        "counts": dict(Counter(e["status"] for e in entries)),
        "sources": dict(source_counts),
        "reason_counts": dict(Counter(r for e in entries for r in e["reasons"])),
        "recovered_from_prior_archive": sum(
            e["status"] == "qualified" and e["original_location"].startswith("archive/")
            for e in entries
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--facts", type=Path)
    parser.add_argument("--evidence", type=Path, nargs="*", default=[])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--structure", type=Path)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--apply", type=Path)
    group.add_argument("--restore", type=Path)
    args = parser.parse_args()
    if args.apply:
        from .quality_transaction import apply

        print(apply(args.root, json.loads(args.apply.read_bytes())))
    elif args.restore:
        from .quality_transaction import restore

        restore(args.root, args.restore)
    else:
        if not args.facts or not args.output:
            parser.error("--facts and --output are required to build a plan")
        plan = build(args.root, args.facts, args.evidence, args.structure)
        args.output.write_text(
            json.dumps(plan, ensure_ascii=True, separators=(",", ":")), encoding="utf-8"
        )
        print(json.dumps({k: v for k, v in plan.items() if k != "entries"}, indent=2))


if __name__ == "__main__":
    main()
