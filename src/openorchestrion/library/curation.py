"""Conservative, reproducible admission to a household listening library.

Admission is an automated suitability assessment, never a claim of human audition.
Source collection, file size and missing descriptive attribution are not rejection
criteria. Originals remain recoverable outside the active assets directory.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re

import mido

from .midi_scan import read_events

POLICY_VERSION = "household-listening-v1"
ADMISSION_FILE = "listening-admission.json"


def admitted_ids(root: Path) -> set[str] | None:
    path = root / ADMISSION_FILE
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("policy_version") != POLICY_VERSION or not isinstance(data.get("asset_ids"), list):
        raise ValueError("invalid listening admission manifest")
    ids = set(data["asset_ids"])
    if any(not isinstance(x, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", x) for x in ids):
        raise ValueError("invalid listening admission asset identity")
    return ids


def assess(facts: dict) -> list[str]:
    """Reasons to archive a candidate; thresholds define scope, not artistic merit."""
    reasons = []
    if facts.get("error"):
        return ["unreadable_or_identity_mismatch"]
    if facts["midi_type"] == 2:
        return ["unsupported_asynchronous_midi"]
    if not facts["notes"]:
        return ["no_musical_notes"]
    if facts["invalid_meter"]:
        reasons.append("invalid_time_signature")
    duration = facts["duration_seconds"]
    if not math.isfinite(duration) or duration <= 0:
        reasons.append("invalid_duration")
    if facts["max_gap_seconds"] > 120:
        reasons.append("extreme_event_gap")
    if duration - facts["last_musical_event_seconds"] > max(30, duration * 0.2):
        reasons.append("excessive_nonmusical_tail")
    if facts["last_note_event_seconds"] < 30 or facts["notes"] < 64:
        reasons.append("short_form_or_sparse_content")
    # Constant-velocity piano transcription without pedal, expression or tempo
    # development is a poor fit for this owner's performance-oriented collection.
    # Organ and ensemble music are deliberately not subjected to this piano rule.
    if (facts["piano_only"] and facts["dominant_velocity_fraction"] >= 0.95
            and not facts["expressive_controls"] and not facts["tempo_development"]):
        reasons.append("mechanical_piano_performance")
    return reasons


def inspect_asset_reference(sidecar: str) -> dict:
    path = Path(sidecar)
    result = {"asset_id": "sha256:" + path.stem}
    try:
        raw_json = path.read_bytes()
        doc = json.loads(raw_json)
        raw = path.with_suffix(".mid").read_bytes()
        if hashlib.sha256(raw).hexdigest() != path.stem or doc["asset_id"] != result["asset_id"]:
            raise ValueError("MIDI/sidecar identity mismatch")
        result.update(sidecar_sha256=hashlib.sha256(raw_json).hexdigest(),
                      title=doc.get("descriptive_metadata", {}).get("title"),
                      source=doc.get("provenance", {}).get("source_label"))
        midi = mido.MidiFile(path.with_suffix(".mid"))
        result["midi_type"] = midi.type
        if midi.type == 2:
            result["reasons"] = assess(result)
            return result
        tempo = 500000
        seconds = 0.0
        last_note = last_musical = max_gap = 0.0
        notes = 0
        invalid_meter = tempo_development = False
        velocities: Counter[int] = Counter()
        patches: Counter[int] = Counter()
        programs: dict[int, int] = defaultdict(int)
        pending_bank: dict[int, list[int]] = defaultdict(lambda: [0, 0])
        banks: dict[int, tuple[int, int]] = defaultdict(lambda: (0, 0))
        controls: dict[int, set[int]] = defaultdict(set)
        percussion = nonzero_note_bank = False
        digest = hashlib.sha256()
        for msg in mido.merge_tracks(midi.tracks):
            gap = mido.tick2second(msg.time, midi.ticks_per_beat, tempo)
            seconds += gap
            max_gap = max(max_gap, gap)
            if msg.is_meta:
                if msg.type == "set_tempo":
                    tempo_development |= seconds > 0 and msg.tempo != tempo
                    tempo = msg.tempo
                if msg.type == "time_signature":
                    invalid_meter |= msg.numerator < 1
                continue
            digest.update(f"{seconds:.6f}:".encode())
            digest.update(bytes(msg.bytes()))
            digest.update(b";")
            if msg.type in {"note_on", "note_off"}:
                last_note = last_musical = seconds
            if msg.type in {"control_change", "pitchwheel", "aftertouch", "polytouch"}:
                last_musical = seconds
            if msg.type == "program_change":
                programs[msg.channel] = msg.program
                banks[msg.channel] = tuple(pending_bank[msg.channel])
            if msg.type == "control_change":
                controls[msg.control].add(msg.value)
                if msg.control in {0, 32}:
                    pending_bank[msg.channel][0 if msg.control == 0 else 1] = msg.value
            if msg.type == "note_on" and msg.velocity > 0:
                notes += 1
                velocities[msg.velocity] += 1
                percussion |= msg.channel == 9
                if msg.channel != 9:
                    patches[programs[msg.channel]] += 1
                    nonzero_note_bank |= any(banks[msg.channel])
        digest.update(f"end:{seconds:.6f}".encode())
        expression = any(len(controls[k]) > 1 for k in (1, 11, 64, 66, 67))
        result.update(duration_seconds=round(seconds, 6),
                      last_note_event_seconds=round(last_note, 6),
                      last_musical_event_seconds=round(last_musical, 6),
                      max_gap_seconds=round(max_gap, 6), notes=notes,
                      invalid_meter=invalid_meter, tempo_development=tempo_development,
                      expressive_controls=expression,
                      dominant_velocity_fraction=max(velocities.values(), default=0) / max(1, notes),
                      piano_only=bool(patches) and all(p < 8 for p in patches)
                      and not percussion and not nonzero_note_bank,
                      playback_fingerprint=digest.hexdigest())
        result["reasons"] = assess(result)
    except Exception as exc:
        result.update(error=f"{type(exc).__name__}: {exc}", reasons=["unreadable_or_identity_mismatch"])
    return result


def inspect_asset(sidecar: str) -> dict:
    path = Path(sidecar)
    result = {"asset_id": "sha256:" + path.stem}
    try:
        raw_json = path.read_bytes()
        doc = json.loads(raw_json)
        raw = path.with_suffix(".mid").read_bytes()
        if hashlib.sha256(raw).hexdigest() != path.stem or doc["asset_id"] != result["asset_id"]:
            raise ValueError("MIDI/sidecar identity mismatch")
        result.update(sidecar_sha256=hashlib.sha256(raw_json).hexdigest(),
                      title=doc.get("descriptive_metadata", {}).get("title"),
                      source=doc.get("provenance", {}).get("source_label"))
        kind, division, events = read_events(raw)
        result["midi_type"] = kind
        if kind == 2:
            result["reasons"] = assess(result)
            return result
        tempo = 500000
        seconds = last_note = last_musical = max_gap = 0.0
        previous_tick = notes = 0
        invalid_meter = tempo_development = percussion = nonzero_note_bank = False
        velocities: Counter[int] = Counter()
        patches: Counter[int] = Counter()
        programs = [0] * 16
        pending_bank = [[0, 0] for _ in range(16)]
        banks = [(0, 0)] * 16
        controls: dict[int, set[int]] = defaultdict(set)
        digest = hashlib.sha256()
        for tick, _, _, status, payload in events:
            # Match mido.tick2second arithmetic to maintain the same fingerprint.
            gap = (tick - previous_tick) * (tempo * 1e-6 / division)
            seconds += gap
            previous_tick = tick
            max_gap = max(max_gap, gap)
            if status == 255:
                if payload[0] == 81:
                    if len(payload) != 4:
                        raise ValueError("invalid tempo event")
                    value = int.from_bytes(payload[1:], "big")
                    if value <= 0:
                        raise ValueError("invalid tempo")
                    tempo_development |= seconds > 0 and value != tempo
                    tempo = value
                if payload[0] == 88:
                    if len(payload) != 5:
                        raise ValueError("invalid time signature")
                    invalid_meter |= payload[1] < 1
                continue
            wire = bytes((status,)) + payload + (b'\xf7' if status == 240 else b'')
            digest.update(f"{seconds:.6f}:".encode())
            digest.update(wire)
            digest.update(b";")
            family, channel = status >> 4, status & 15
            if family in (8, 9):
                last_note = last_musical = seconds
            if family in (10, 11, 13, 14):
                last_musical = seconds
            if family == 12:
                programs[channel] = payload[0]
                banks[channel] = tuple(pending_bank[channel])
            if family == 11:
                control, value = payload
                controls[control].add(value)
                if control in (0, 32):
                    pending_bank[channel][0 if control == 0 else 1] = value
            if family == 9 and payload[1] > 0:
                notes += 1
                velocities[payload[1]] += 1
                percussion |= channel == 9
                if channel != 9:
                    patches[programs[channel]] += 1
                    nonzero_note_bank |= any(banks[channel])
        digest.update(f"end:{seconds:.6f}".encode())
        result.update(duration_seconds=round(seconds, 6), last_note_event_seconds=round(last_note, 6),
                      last_musical_event_seconds=round(last_musical, 6), max_gap_seconds=round(max_gap, 6),
                      notes=notes, invalid_meter=invalid_meter, tempo_development=tempo_development,
                      expressive_controls=any(len(controls[k]) > 1 for k in (1, 11, 64, 66, 67)),
                      dominant_velocity_fraction=max(velocities.values(), default=0) / max(1, notes),
                      piano_only=bool(patches) and all(p < 8 for p in patches)
                      and not percussion and not nonzero_note_bank,
                      playback_fingerprint=digest.hexdigest())
        result["reasons"] = assess(result)
    except Exception:
        # The playback parser accepts some noncanonical encodings (for example
        # padded/short meta messages). Never exclude music just because this
        # optimized offline reader is stricter than the established parser.
        return inspect_asset_reference(sidecar)
    return result


def make_plan(root: Path, workers: int = 2) -> dict:
    files = sorted((root / "assets").glob("*.json"))
    entries = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for index, result in enumerate(pool.map(inspect_asset, map(str, files), chunksize=8), 1):
            entries.append(result)
            if index % 500 == 0:
                print(f"Inspected {index}/{len(files)}", flush=True)
    # Only collapse byte-equivalent timed playback streams, not same-name works
    # or loosely similar arrangements. Retain distinct expressive performances.
    seen = {}
    for entry in entries:
        if entry["reasons"]:
            continue
        key = entry["playback_fingerprint"]
        if key in seen:
            entry["reasons"] = ["duplicate_timed_playback"]
            entry["retained_asset_id"] = seen[key]
        else:
            seen[key] = entry["asset_id"]
    return {"policy_version": POLICY_VERSION, "library_root": str(root.resolve()),
            "created_at": datetime.now(timezone.utc).isoformat(), "entries": entries,
            "counts": {"inspected": len(entries), "admitted": sum(not e["reasons"] for e in entries),
                       "archived": sum(bool(e["reasons"]) for e in entries)},
            "reason_counts": dict(Counter(r for e in entries for r in e["reasons"]))}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--workers", type=int, choices=(1, 2), default=2)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--apply-plan", type=Path, help="Publish a plan with playback and library writers stopped")
    actions.add_argument("--restore-run", type=Path, help="Undo an unchanged latest run with playback stopped")
    args = parser.parse_args()
    if args.apply_plan:
        from .curation_transaction import apply_plan
        print(apply_plan(args.library_root, json.loads(args.apply_plan.read_text(encoding="utf-8"))))
        return
    if args.restore_run:
        from .curation_transaction import restore_run
        restore_run(args.library_root, args.restore_run)
        print("Restored", args.restore_run)
        return
    if args.output is None:
        parser.error("--output is required for a scan")
    plan = make_plan(args.library_root, args.workers)
    args.output.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"counts": plan["counts"], "reasons": plan["reason_counts"]}))


if __name__ == "__main__":
    main()
