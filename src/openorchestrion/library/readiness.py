"""Versioned, disposable playback facts. Never modifies MIDI, metadata or admission.

Parts are MIDI channels, not guessed musical roles. Program/controller state is
shared across tracks. Bank selection takes effect at the next program change.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sqlite3
from collections import Counter
from contextlib import closing
from pathlib import Path

from ..midi.gm import GM_PROGRAM_NAMES
from ..playback.rendering import RenderingMode, RenderingPolicy
from .midi_scan import read_events

VERSION = 1
LIMITATION = (
    "Structural MIDI evidence, not a listening-quality rating. Simultaneous notes "
    "include sustain but cannot predict sample layers, release tails or the keyboard's "
    "actual voice allocation. Repeated pitches count once per channel."
)


def analyze_parts(raw: bytes) -> dict:
    kind, division, events = read_events(raw)
    if kind == 2:
        raise ValueError("asynchronous MIDI tracks have no single playback timeline")
    names = {}
    parts = {}
    banks = [[0, 0] for _ in range(16)]
    programs = [(0, 0, 0, True) for _ in range(16)]
    keyed = [set() for _ in range(16)]
    held = [set() for _ in range(16)]
    pedal = [False] * 16
    peaks = [0] * 16
    sustain = set()
    bend = set()
    peak = melodic_peak = sysex = 0
    total = 0
    tick_before = 0
    seconds = 0.0
    tempo = 500000
    for tick, track, _, status, data in events:
        seconds += (tick - tick_before) * tempo / (division * 1000000)
        tick_before = tick
        if status == 255:
            if data[0] == 3:
                names.setdefault(track, data[1:].decode("latin1"))
            elif data[0] == 81 and len(data) == 4:
                tempo = int.from_bytes(data[1:], "big")
            continue
        if status == 240:
            sysex += 1
            continue
        ch, op = status & 15, status >> 4
        before = len(keyed[ch]) + len(held[ch])
        if op == 11:
            cc, value = data
            if cc in (0, 32):
                banks[ch][cc == 32] = value
            elif cc == 64:
                pedal[ch] = value >= 64
                if pedal[ch]:
                    sustain.add(ch)
                else:
                    held[ch].clear()
            elif cc == 120:
                keyed[ch].clear()
                held[ch].clear()
                pedal[ch] = False
            elif cc == 123:
                if pedal[ch]:
                    held[ch].update(keyed[ch])
                keyed[ch].clear()
            elif cc == 121:
                pedal[ch] = False
                held[ch].clear()
        elif op == 12:
            programs[ch] = (data[0], *banks[ch], False)
        elif op == 14:
            bend.add(ch)
        elif op == 9 and data[1] > 0:
            part = parts.setdefault(ch, {"tracks": set(), "sounds": Counter(), "notes": [], "velocities": []})
            part["tracks"].add(track)
            part["sounds"][programs[ch]] += 1
            part["notes"].append(data[0])
            part["velocities"].append(data[1])
            held[ch].discard(data[0])
            keyed[ch].add(data[0])
        elif op in (8, 9):
            if data[0] in keyed[ch]:
                keyed[ch].discard(data[0])
                if pedal[ch]:
                    held[ch].add(data[0])
        after = len(keyed[ch]) + len(held[ch])
        total += after - before
        peaks[ch] = max(peaks[ch], after)
        peak = max(peak, total)
        melodic_peak = max(melodic_peak, total - len(keyed[9]) - len(held[9]))
    result = []
    for ch, part in sorted(parts.items()):
        sounds = []
        for (program, msb, lsb, implicit), count in part["sounds"].items():
            sounds.append({
                "program": program + 1, "name": (
                    "Standard drum kit" if ch == 9 and program == 0 and msb == lsb == 0
                    else "Device-dependent drum kit" if ch == 9 else GM_PROGRAM_NAMES[program]
                ), "bank_msb": msb, "bank_lsb": lsb,
                "implicit": implicit, "note_count": count,
            })
        result.append({
            "channel": ch + 1, "percussion": ch == 9,
            "tracks": [{"index": t, "name": names.get(t)} for t in sorted(part["tracks"])],
            "sounds": sounds, "note_count": len(part["notes"]),
            "note_min": min(part["notes"]), "note_max": max(part["notes"]),
            "velocity_min": min(part["velocities"]), "velocity_max": max(part["velocities"]),
            "sustain": ch in sustain, "pitch_bend": ch in bend, "peak_notes": peaks[ch],
        })
    return {"version": VERSION, "parts": result, "peak_notes": peak,
            "melodic_peak_notes": melodic_peak, "sysex_count": sysex,
            "duration_seconds": round(seconds, 6)}


def _signature(path: Path) -> str:
    stat = path.stat()
    return f"{stat.st_dev}:{stat.st_ino}:{stat.st_size}:{stat.st_mtime_ns}:{stat.st_ctime_ns}"


def source_facts(catalog: Path, asset_id: str, midi_path: str) -> dict:
    path = Path(midi_path)
    signature = _signature(path)
    cache = catalog.with_name("playback-facts.sqlite3")
    if cache.is_file():
        try:
            with closing(sqlite3.connect(f"{cache.as_uri()}?mode=ro", uri=True)) as conn:
                row = conn.execute(
                    "SELECT facts FROM facts WHERE asset_id=? AND version=? AND signature=?",
                    (asset_id, VERSION, signature),
                ).fetchone()
            if row:
                return json.loads(row[0])
        except (sqlite3.Error, ValueError):
            pass  # A missing/old/corrupt disposable index must not hide the song.
    raw = path.read_bytes()
    if _signature(path) != signature:
        raise ValueError("MIDI changed during analysis; retry after the write completes")
    if asset_id != "sha256:" + hashlib.sha256(raw).hexdigest():
        raise ValueError("MIDI content no longer matches the admitted asset")
    return analyze_parts(raw)


def readiness(facts: dict, performance_type: str | None, policy: RenderingPolicy | None = None) -> dict:
    policy = policy or RenderingPolicy()
    parts = copy.deepcopy(facts["parts"])
    overrides = {p.channel + 1: p.program for p in policy.program_overrides}
    if policy.mode == RenderingMode.PIANO_ONLY:
        parts = [p for p in parts if not p["percussion"]]
    for part in parts:
        program = overrides.get(part["channel"])
        if program is None and policy.mode == RenderingMode.PIANO_ONLY:
            program = policy.piano_program
        part["changed"] = program is not None
        if program is not None:
            part["sounds"] = [{"program": program + 1, "name": GM_PROGRAM_NAMES[program],
                               "bank_msb": 0, "bank_lsb": 0, "implicit": False,
                               "note_count": part["note_count"]}]
    flags = []

    def flag(code, severity, message):
        flags.append({"code": code, "severity": severity, "message": message})

    peak = facts["melodic_peak_notes"] if policy.mode == RenderingMode.PIANO_ONLY else facts["peak_notes"]
    if not parts:
        flag("no_sounding_parts", "warning", "This sound setting leaves no sounding notes.")
    if policy.mode == RenderingMode.PIANO_ONLY and any(p["percussion"] for p in facts["parts"]):
        flag("percussion_suppressed", "info", "Piano Only omits the source percussion part; it does not turn drum note numbers into piano pitches.")
    if peak > 48:
        flag("wk220_over_48", "warning", f"Estimated peak {peak} notes exceeds the WK-220's nominal 48-voice capacity; notes may be stolen.")
    elif peak > 24:
        flag("wk220_over_24", "info", f"Estimated peak {peak} notes: some WK-220 tones have a 24-voice limit; sound choice matters.")
    if any(s["bank_msb"] or s["bank_lsb"] or (p["percussion"] and s["program"] != 1) for p in parts for s in p["sounds"]):
        flag("unverified_sound_mapping", "warning", "Non-default banks or drum kits need device-specific mapping. GM names identify the program slot; the actual sound is unverified.")
    if facts["sysex_count"]:
        flag("sysex_blocked", "info", "Device setup in SysEx is blocked by the player; the source may expect sounds or effects that will not be configured.")
    if any(s["implicit"] for p in parts for s in p["sounds"]):
        flag("default_program", "info", "Some notes precede any program change. The player starts pitched channels on Acoustic Grand Piano and channel 10 on its default drum kit.")
    # A clue about source completeness, never an automatic quality verdict.
    if performance_type == "MULTI_INSTRUMENT" and len(facts["parts"]) < 2:
        flag("sparse_arrangement", "info", "The catalog describes multiple instruments but the source uses only one sounding channel. This may be a reduction, sequential sounds or an incomplete export.")
    return {"version": VERSION, "status": "caution" if any(f["severity"] == "warning" for f in flags) else "structurally_playable",
            "parts": parts, "peak_notes": peak, "flags": flags, "limitation": LIMITATION,
            "reference_device": "Casio WK-220 (reference limits; not automatic device identification)"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build disposable playback facts for every admitted asset.")
    parser.add_argument("catalog", type=Path)
    parser.add_argument("--library-root", type=Path, help="Defaults to the catalog's directory")
    args = parser.parse_args()
    db = args.catalog.resolve()
    with closing(sqlite3.connect(f"{db.as_uri()}?mode=ro", uri=True)) as catalog:
        rows = catalog.execute("SELECT asset_id,midi_path,performance_type FROM assets ORDER BY asset_id").fetchall()
    counts = Counter()
    cache = db.with_name("playback-facts.sqlite3")
    with closing(sqlite3.connect(cache)) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS facts (asset_id TEXT PRIMARY KEY,version INTEGER,signature TEXT,facts TEXT)")
        for index, (asset_id, path, arrangement) in enumerate(rows):
            path = str((args.library_root or db.parent) / path)
            try:
                signature = _signature(Path(path))
                facts = source_facts(db, asset_id, path)
                if _signature(Path(path)) != signature:
                    raise ValueError("MIDI changed during indexing")
                conn.execute("INSERT OR REPLACE INTO facts VALUES (?,?,?,?)", (asset_id, VERSION, signature, json.dumps(facts)))
                counts.update(f["code"] for f in readiness(facts, arrangement)["flags"])
                counts["indexed"] += 1
            except (OSError, ValueError) as exc:
                counts["failed"] += 1
                print(json.dumps({"asset_id": asset_id, "error": str(exc)}), flush=True)
            if index % 250 == 0:
                conn.commit()
                print(json.dumps({"processed": index + 1, "total": len(rows)}), flush=True)
        conn.commit()
    print(json.dumps({"version": VERSION, "total": len(rows), "counts": counts}, sort_keys=True), flush=True)
    if counts["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
