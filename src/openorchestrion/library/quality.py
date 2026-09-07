"""Evidence-based full-song admission. Original bytes are never repaired in place.

Facts, provenance evidence, musical suitability and device limitations are separate.
An unresolved candidate is excluded from automatic listening, not declared worthless.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
import argparse
import hashlib
import json
from pathlib import Path
import re
import time

from .midi_scan import read_events

VERSION = "complete-listening-v2"


def analyze(raw: bytes) -> dict:
    kind, division, events = read_events(raw)
    if kind == 2:
        raise ValueError("asynchronous sequences are not a complete common timeline")
    parts = {}
    keyed = [set() for _ in range(16)]
    held = [set() for _ in range(16)]
    latched = [set() for _ in range(16)]
    sustain = [False] * 16
    sostenuto = [False] * 16
    pending = [[0, 0] for _ in range(16)]
    patch = [(0, 0, 0, True)] * 16
    controls = defaultdict(set)
    meta = Counter()
    names = {}
    tempo, previous, seconds = 500000, 0, 0.0
    first_attack = last_attack = last_release = None
    attacks = []
    gaps = []
    silent_at = 0.0
    sounding = peak = 0
    sysex = []
    fingerprint = hashlib.sha256()
    for tick, track, _, status, data in events:
        seconds += (tick - previous) * tempo / (division * 1000000)
        previous = tick
        if status == 255:
            meta[str(data[0])] += 1
            if data[0] == 81:
                if len(data) != 4 or int.from_bytes(data[1:], "big") <= 0:
                    raise ValueError("invalid tempo")
                tempo = int.from_bytes(data[1:], "big")
            elif data[0] == 3:
                names[track] = data[1:].decode("latin1").strip()
            continue
        fingerprint.update(f"{seconds:.6f}:".encode() + bytes([status]) + data + b";")
        if status == 240:
            sysex.append(data.hex())
            continue
        ch, op = status & 15, status >> 4
        before = len(keyed[ch] | held[ch])
        if op == 11:
            cc, value = data
            controls[ch, cc].add(value)
            if cc in (0, 32):
                pending[ch][int(cc == 32)] = value
            elif cc == 64:
                sustain[ch] = value >= 64
                if not sustain[ch]:
                    held[ch].intersection_update(latched[ch])
            elif cc == 66:
                down = value >= 64
                if down and not sostenuto[ch]:
                    latched[ch] = set(keyed[ch])
                elif not down:
                    latched[ch].clear()
                    if not sustain[ch]:
                        held[ch].clear()
                sostenuto[ch] = down
            elif cc in (120, 121, 123):
                if cc == 123:
                    held[ch].update(keyed[ch] if sustain[ch] else keyed[ch] & latched[ch])
                    keyed[ch].clear()
                else:
                    held[ch].clear()
                    latched[ch].clear()
                    sustain[ch] = sostenuto[ch] = False
                    if cc == 120:
                        keyed[ch].clear()
        elif op == 12:
            patch[ch] = (data[0], *pending[ch], False)
        elif op == 9 and data[1]:
            part = parts.setdefault(
                ch,
                {
                    "velocity": Counter(),
                    "patches": Counter(),
                    "tracks": set(),
                    "pitches": set(),
                    "attacks": [],
                    "pressure": False,
                    "bend": False,
                },
            )
            part["velocity"][data[1]] += 1
            part["patches"][patch[ch]] += 1
            part["tracks"].add(track)
            part["pitches"].add(data[0])
            part["attacks"].append(seconds)
            attacks.append(seconds)
            first_attack = seconds if first_attack is None else first_attack
            last_attack = seconds
            keyed[ch].add(data[0])
            held[ch].discard(data[0])
        elif op in (8, 9):
            if data[0] in keyed[ch]:
                keyed[ch].discard(data[0])
                if sustain[ch] or data[0] in latched[ch]:
                    held[ch].add(data[0])
                last_release = seconds
        if ch in parts:
            parts[ch]["pressure"] |= op in (10, 13)
            parts[ch]["bend"] |= op == 14
        # Drum note-off conventions vary; do not let unclosed drum hits hide rests.
        if ch != 9:
            after = len(keyed[ch] | held[ch])
            was = sounding
            sounding += after - before
            peak = max(peak, sounding)
            if not was and sounding and silent_at is not None:
                gaps.append(seconds - silent_at)
            if was and not sounding:
                silent_at = seconds
    fingerprint.update(f"end:{seconds:.6f}".encode())
    output = []
    span = max(0.001, (last_attack or 0) - (first_attack or 0))
    for ch, part in sorted(parts.items()):
        velocity = part["velocity"]
        count = sum(velocity.values())
        cc = [
            {"cc": k, "min": min(v), "max": max(v), "distinct": len(v)}
            for (c, k), v in sorted(controls.items())
            if c == ch
        ]
        output.append(
            {
                "channel": ch + 1,
                "percussion": ch == 9,
                "notes": count,
                "velocity_values": len(velocity),
                "dominant_velocity_fraction": round(max(velocity.values()) / count, 6),
                "velocity_min": min(velocity),
                "velocity_max": max(velocity),
                "note_min": min(part["pitches"]),
                "note_max": max(part["pitches"]),
                "unique_pitches": len(part["pitches"]),
                "patches": [
                    {"program": p + 1, "msb": m, "lsb": lsb, "implicit": i, "notes": n}
                    for (p, m, lsb, i), n in part["patches"].items()
                ],
                "tracks": [{"index": t, "name": names.get(t)} for t in sorted(part["tracks"])],
                "controllers": cc,
                "pitch_bend": part["bend"],
                "pressure": part["pressure"],
                "occupied_sections": len(
                    {min(11, int((t - (first_attack or 0)) / span * 12)) for t in part["attacks"]}
                ),
                "unreleased_keys": len(keyed[ch]) if ch != 9 else 0,
                "pedal_held_at_end": len(held[ch]) if ch != 9 else 0,
            }
        )
    # Reset-only SysEx is distinguished from unknown device-dependent setup.
    gm_resets = {"7e7f0901", "7e7f0902", "7e7f0903"}
    return {
        "format": kind,
        "division": division,
        "duration": round(seconds, 6),
        "notes": len(attacks),
        "first_attack": first_attack,
        "last_attack": last_attack,
        "last_release": last_release,
        "longest_silence": round(max(gaps[1:], default=0), 6),
        "peak_pitched_notes": peak,
        "parts": output,
        "meta_counts": dict(meta),
        "sysex_count": len(sysex),
        "unknown_sysex": sum(s.rstrip("f7") not in gm_resets for s in sysex),
        "fingerprint": fingerprint.hexdigest(),
    }


def inspect(path: str) -> dict:
    sidecar = Path(path)
    result = {"asset_id": "sha256:" + sidecar.stem}
    try:
        metadata = sidecar.read_bytes()
        doc = json.loads(metadata)
        raw = sidecar.with_suffix(".mid").read_bytes()
        if hashlib.sha256(raw).hexdigest() != sidecar.stem or doc["asset_id"] != result["asset_id"]:
            raise ValueError("identity mismatch")
        result.update(
            sidecar_sha256=hashlib.sha256(metadata).hexdigest(),
            title=doc.get("descriptive_metadata", {}).get("title"),
            descriptive=doc.get("descriptive_metadata", {}),
            original_filename=doc["file"]["original_filename"],
            provenance=doc.get("provenance", {}),
        )
        result["facts"] = analyze(raw)
    except Exception as error:
        result["error"] = f"{type(error).__name__}: {error}"
    return result


def decide(entry: dict, evidence: dict | None = None) -> dict:
    evidence = evidence or {}
    reasons, warnings = [], []
    if entry.get("error"):
        return {
            "status": "excluded",
            "reasons": ["unreadable_or_unsupported"],
            "evidence": [],
            "warnings": [],
        }
    f = entry["facts"]
    pitched = [p for p in f["parts"] if not p["percussion"]]
    if not f["notes"] or not pitched:
        reasons.append("no_pitched_arrangement")
    if any(p["unreleased_keys"] for p in pitched):
        reasons.append("unresolved_note_endings")
    if f["longest_silence"] > max(20, f["duration"] * 0.15):
        reasons.append("unexplained_internal_silence")
    if f["last_release"] is not None and f["duration"] - f["last_release"] > max(
        20, f["duration"] * 0.15
    ):
        reasons.append("excessive_tail")
    patches = [s for p in f["parts"] for s in p["patches"]]
    if any(s["msb"] or s["lsb"] for s in patches):
        warnings.append("unverified_sound_bank")
    if any(s["program"] != 1 for p in f["parts"] if p["percussion"] for s in p["patches"]):
        warnings.append("unverified_drum_kit")
    if f["unknown_sysex"]:
        warnings.append("unverified_device_setup")
    if f["peak_pitched_notes"] > 48:
        warnings.append("wk220_voice_capacity_risk")
    if any(p["pedal_held_at_end"] for p in pitched):
        warnings.append("pedal_release_needed_at_stop")
    # No source-wide blanket admission. Completeness needs an asset-specific record.
    proof = evidence.get(entry["asset_id"])
    if not proof or proof.get("completeness") != "complete":
        reasons.append("completeness_unresolved")
    if proof and proof.get("completeness") == "partial":
        reasons = [r for r in reasons if r != "completeness_unresolved"] + [
            "confirmed_partial_arrangement"
        ]
    # Performance capture proof is stronger than event-count heuristics.
    expressive = bool(proof and proof.get("performance_capture"))
    expressive_notes = 0
    for p in pitched:
        relevant = [
            c
            for c in p["controllers"]
            if c["cc"] in (1, 2, 7, 11, 64, 66, 67) and c["distinct"] > 1
        ]
        if p["notes"] >= 32 and (
            p["velocity_values"] >= 8 and p["dominant_velocity_fraction"] < 0.9 or relevant
        ):
            expressive_notes += p["notes"]
    expressive |= expressive_notes >= max(1, sum(p["notes"] for p in pitched) * 0.5)
    if proof and proof.get("published_instrumentation"):
        instrumentation = proof["published_instrumentation"].lower()
        requirements = {
            "piano": set(range(1, 9)),
            "harpsichord": {7},
            "organ": set(range(17, 25)),
            "guitar": set(range(25, 33)),
            "violin": {41},
            "viola": {42},
            "cello": {43},
            "violoncello": {43},
            "flute": {73, 74},
            "oboe": {69},
            "clarinet": {72},
            "bassoon": {71},
            "trumpet": {57},
            "trombone": {58},
            "horn": {61},
            "voice": {53, 54, 55},
        }
        requested = {s["program"] for p in pitched for s in p["patches"]}
        required = [
            programs
            for name, programs in requirements.items()
            if re.search(r"\b" + name + r"\b", instrumentation)
        ]
        if "string quartet" in instrumentation:
            required += [{41}, {42}, {43}]
        if required and not all(requested & programs for programs in required):
            reasons.append("published_instrument_assignment_unresolved")
    if not expressive:
        reasons.append("insufficient_performance_expression")
    if f["duration"] <= 0:
        reasons.append("invalid_duration")
    return {
        "status": "qualified"
        if not reasons
        else "excluded"
        if any(
            r in reasons
            for r in (
                "no_pitched_arrangement",
                "confirmed_partial_arrangement",
                "unreadable_or_unsupported",
            )
        )
        else "unresolved",
        "reasons": sorted(set(reasons)),
        "warnings": warnings,
        "evidence": [proof] if proof else [],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    paths = sorted(args.root.glob("assets/*.json")) + sorted(
        args.root.glob("archive/*/assets/*.json")
    )
    if len({p.stem for p in paths}) != len(paths):
        raise ValueError("duplicate original identities in snapshot")
    start = time.monotonic()
    with (
        args.output.open("w", encoding="utf-8") as out,
        ProcessPoolExecutor(max_workers=args.workers) as pool,
    ):
        for i, (path, result) in enumerate(
            zip(paths, pool.map(inspect, map(str, paths), chunksize=8)), 1
        ):
            result["original_location"] = path.relative_to(args.root).as_posix()
            out.write(json.dumps(result, ensure_ascii=True, separators=(",", ":")) + "\n")
            if i % 500 == 0:
                out.flush()
                print(
                    json.dumps(
                        {
                            "scanned": i,
                            "total": len(paths),
                            "seconds": round(time.monotonic() - start, 1),
                        }
                    ),
                    flush=True,
                )
    print(
        json.dumps({"scanned": len(paths), "seconds": round(time.monotonic() - start, 1)}),
        flush=True,
    )


if __name__ == "__main__":
    main()
