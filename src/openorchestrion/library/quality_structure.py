"""Arrangement evidence independent of publisher identity; not an artistic rating."""

from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
import argparse
import json
from pathlib import Path
import statistics

from .midi_scan import read_events


def structure(raw):
    _, division, events = read_events(raw)
    tempo = 500000
    previous = 0
    seconds = 0.0
    rows = defaultdict(list)
    starts = {}
    durations = defaultdict(list)
    volume = [100] * 16
    expression = [127] * 16
    muted = Counter()
    for tick, track, seq, status, data in events:
        seconds += (tick - previous) * tempo / (division * 1000000)
        previous = tick
        if status == 255:
            if data[0] == 81:
                tempo = int.from_bytes(data[1:], "big")
            continue
        if status == 240:
            continue
        ch, op = status & 15, status >> 4
        if op == 11 and data[0] in (7, 11):
            (volume if data[0] == 7 else expression)[ch] = data[1]
        if op == 9 and data[1]:
            if not volume[ch] or not expression[ch]:
                muted[ch] += 1
                continue
            rows[ch].append((seconds, data[0], data[1]))
            starts[ch, data[0]] = seconds
        elif op in (8, 9) and (ch, data[0]) in starts:
            durations[ch].append(max(0, seconds - starts.pop((ch, data[0]))))
    all_times = [t for values in rows.values() for t, p, v in values]
    if not all_times:
        return {"parts": []}
    first, last = min(all_times), max(all_times)
    span = max(0.001, last - first)
    parts = []
    for ch, values in sorted(rows.items()):
        sections = defaultdict(list)
        for t, p, v in values:
            sections[min(11, int((t - first) / span * 12))].append(p)
        onsets = Counter(round(t, 4) for t, p, v in values)
        pitches = sorted(p for t, p, v in values)
        notes = len(values)
        parts.append(
            {
                "channel": ch + 1,
                "notes": notes,
                "muted_notes": muted[ch],
                "median_pitch": statistics.median(pitches),
                "unique_pitches": len(set(pitches)),
                "range": pitches[-1] - pitches[0],
                "chord_fraction": round(sum(n for n in onsets.values() if n >= 2) / notes, 4),
                "sections": len(sections),
                "broad_register_sections": sum(max(v) - min(v) >= 24 for v in sections.values()),
                "duration_values": len({round(v, 2) for v in durations[ch]}),
                "zero_length_notes": sum(v <= 0 for v in durations[ch]),
                "median_duration": statistics.median(durations[ch]) if durations[ch] else None,
            }
        )
    return {"parts": parts, "first_audible_attack": first, "last_audible_attack": last}


def infer(entry, measured):
    """Positive evidence for a self-contained rendition; do not claim source identity."""
    f = entry.get("facts", {})
    parts = {p["channel"]: p for p in f.get("parts", [])}
    metrics = {p["channel"]: p for p in measured.get("parts", []) if p["channel"] != 10}
    if f.get("duration", 0) < 90 or f.get("notes", 0) < 300:
        return None
    if any(
        p["muted_notes"] > p["notes"] * 0.05 or p["zero_length_notes"] > p["notes"] * 0.01
        for p in metrics.values()
    ):
        return None

    def programs(ch):
        return {p["program"] for p in parts[ch]["patches"]}

    def explicit(ch):
        return all(not p["implicit"] and p["msb"] == p["lsb"] == 0 for p in parts[ch]["patches"])

    pitched = [ch for ch in metrics if ch in parts]
    # A substantial, articulated, two-register piano arrangement spanning the
    # piece is stronger evidence than one channel or one default patch alone.
    if pitched and all(programs(ch) <= {1, 2} and explicit(ch) for ch in pitched):
        for ch in pitched:
            p = metrics[ch]
            if (
                p["notes"] >= 500
                and p["unique_pitches"] >= 24
                and p["chord_fraction"] >= 0.2
                and p["broad_register_sections"] >= 9
                and p["sections"] >= 11
                and p["duration_values"] >= 8
            ):
                return {
                    "completeness": "complete",
                    "performance_capture": False,
                    "inference": True,
                    "basis": "Self-contained piano arrangement supported by sustained two-register writing, chords and articulation across the timeline",
                    "source": entry.get("provenance", {}).get("source_reference", ""),
                    "arrangement": "solo_piano",
                    "role_channels": {"piano": ch},
                }
    bass = [
        ch
        for ch in pitched
        if explicit(ch)
        and programs(ch) & set(range(33, 41))
        and metrics[ch]["notes"] >= 100
        and metrics[ch]["median_pitch"] <= 55
        and metrics[ch]["sections"] >= 8
        and metrics[ch]["unique_pitches"] >= 8
    ]
    harmony = [
        ch
        for ch in pitched
        if explicit(ch)
        and programs(ch) & (set(range(1, 33)) | set(range(41, 57)) | set(range(89, 97)))
        and metrics[ch]["notes"] >= 150
        and metrics[ch]["chord_fraction"] >= 0.3
        and metrics[ch]["sections"] >= 8
    ]
    lead = [
        ch
        for ch in pitched
        if explicit(ch)
        and metrics[ch]["notes"] >= 150
        and metrics[ch]["median_pitch"] >= 60
        and metrics[ch]["unique_pitches"] >= 12
        and metrics[ch]["chord_fraction"] <= 0.3
        and metrics[ch]["sections"] >= 8
        and metrics[ch]["duration_values"] >= 6
    ]
    for b in bass:
        for h in harmony:
            for melody in lead:
                if len({b, h, melody}) == 3:
                    return {
                        "completeness": "complete",
                        "performance_capture": False,
                        "inference": True,
                        "basis": "Self-contained ensemble arrangement supported by distinct sustained melody, bass and chordal accompaniment across the timeline",
                        "source": entry.get("provenance", {}).get("source_reference", ""),
                        "arrangement": "ensemble",
                        "role_channels": {"bass": b, "harmony": h, "melody": melody},
                    }
    return None


def inspect(path):
    try:
        return structure(Path(path).read_bytes())
    except Exception as exc:
        return {"error": str(exc), "parts": []}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("facts", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    records = [json.loads(line) for line in args.facts.open(encoding="utf-8")]
    paths = [str((args.root / r["original_location"]).with_suffix(".mid")) for r in records]
    with args.output.open("w", encoding="utf-8") as out, ProcessPoolExecutor(max_workers=6) as pool:
        for i, (record, result) in enumerate(
            zip(records, pool.map(inspect, paths, chunksize=8)), 1
        ):
            out.write(
                json.dumps(
                    {
                        "asset_id": record["asset_id"],
                        "structure": result,
                        "inference": infer(record, result),
                    }
                )
                + "\n"
            )
            if i % 1000 == 0:
                out.flush()
                print(i, flush=True)


if __name__ == "__main__":
    main()
