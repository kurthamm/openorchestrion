from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from mido import Message, MetaMessage, MidiFile, MidiTrack, bpm2tempo

TICKS_PER_BEAT = 480
DEFAULT_BPM = 120
QUARTER = TICKS_PER_BEAT
EIGHTH = TICKS_PER_BEAT // 2
HALF = TICKS_PER_BEAT * 2


@dataclass(frozen=True, slots=True)
class GeneratedFixture:
    name: str
    filename: str
    purpose: str
    expected: dict[str, object]


def _base_midi(name: str, *, midi_type: int = 1, bpm: int = DEFAULT_BPM) -> MidiFile:
    midi = MidiFile(type=midi_type, ticks_per_beat=TICKS_PER_BEAT)
    conductor = MidiTrack()
    conductor.append(MetaMessage("track_name", name="conductor", time=0))
    conductor.append(MetaMessage("text", text=f"OpenOrchestrion synthetic fixture: {name}", time=0))
    conductor.append(MetaMessage("time_signature", numerator=4, denominator=4, time=0))
    conductor.append(MetaMessage("set_tempo", tempo=bpm2tempo(bpm), time=0))
    midi.tracks.append(conductor)
    return midi


def _named_track(name: str) -> MidiTrack:
    track = MidiTrack()
    track.append(MetaMessage("track_name", name=name, time=0))
    return track


def _note(
    track: MidiTrack,
    note: int,
    *,
    channel: int = 0,
    velocity: int = 96,
    duration: int = QUARTER,
    delay: int = 0,
) -> None:
    track.append(Message("note_on", channel=channel, note=note, velocity=velocity, time=delay))
    track.append(Message("note_off", channel=channel, note=note, velocity=0, time=duration))


def single_note() -> MidiFile:
    midi = _base_midi("single-note")
    track = _named_track("single-note")
    _note(track, 60, velocity=96, duration=HALF)
    midi.tracks.append(track)
    return midi


def velocity_ladder() -> MidiFile:
    midi = _base_midi("velocity-ladder")
    track = _named_track("velocity-ladder")
    for index, velocity in enumerate((20, 45, 70, 95, 120)):
        _note(
            track,
            60,
            velocity=velocity,
            duration=QUARTER,
            delay=0 if index == 0 else EIGHTH,
        )
    midi.tracks.append(track)
    return midi


def sustain_cc64() -> MidiFile:
    midi = _base_midi("sustain-cc64", bpm=90)
    track = _named_track("sustain-cc64")
    track.append(Message("control_change", channel=0, control=64, value=127, time=0))
    chord = (60, 64, 67)
    for note in chord:
        track.append(Message("note_on", channel=0, note=note, velocity=92, time=0))
    for index, note in enumerate(chord):
        track.append(
            Message(
                "note_off",
                channel=0,
                note=note,
                velocity=0,
                time=HALF if index == 0 else 0,
            )
        )
    track.append(Message("control_change", channel=0, control=64, value=0, time=HALF))
    midi.tracks.append(track)
    return midi


def program_change() -> MidiFile:
    midi = _base_midi("program-change")
    track = _named_track("program-change")
    programs = (
        (0, "Acoustic Grand Piano"),
        (33, "Electric Bass (finger)"),
        (48, "String Ensemble 1"),
        (56, "Trumpet"),
    )
    for index, (program, label) in enumerate(programs):
        track.append(MetaMessage("marker", text=label, time=0 if index == 0 else EIGHTH))
        track.append(Message("control_change", channel=0, control=0, value=0, time=0))
        track.append(Message("control_change", channel=0, control=32, value=0, time=0))
        track.append(Message("program_change", channel=0, program=program, time=0))
        _note(track, 60, velocity=92, duration=QUARTER)
    midi.tracks.append(track)
    return midi


def gm_ensemble() -> MidiFile:
    midi = _base_midi("gm-ensemble", bpm=112)

    parts = (
        ("piano", 0, 0, (60, 64, 67, 72)),
        ("bass", 1, 33, (36, 36, 43, 41)),
        ("strings", 2, 48, (55, 59, 62, 67)),
        ("trumpet", 3, 56, (67, 69, 71, 72)),
        ("alto-sax", 4, 65, (64, 67, 69, 67)),
    )
    for name, channel, program, notes in parts:
        track = _named_track(name)
        track.append(Message("program_change", channel=channel, program=program, time=0))
        for note in notes:
            _note(track, note, channel=channel, velocity=88, duration=QUARTER)
        midi.tracks.append(track)

    drums = _named_track("percussion-channel-10")
    for note in (36, 42, 38, 42, 36, 42, 38, 46):
        _note(drums, note, channel=9, velocity=100, duration=EIGHTH)
    midi.tracks.append(drums)
    return midi


def note_range() -> MidiFile:
    midi = _base_midi("note-range", bpm=100)
    track = _named_track("note-range")
    for note in (0, 12, 21, 36, 60, 84, 108, 127):
        track.append(MetaMessage("marker", text=f"MIDI note {note}", time=EIGHTH if note else 0))
        _note(track, note, velocity=90, duration=QUARTER)
    midi.tracks.append(track)
    return midi


def polyphony_stress(voices: int) -> MidiFile:
    if not 1 <= voices <= 104:
        raise ValueError("voices must be between 1 and 104")
    midi = _base_midi(f"polyphony-{voices}", bpm=80)
    track = _named_track(f"polyphony-{voices}")
    first_note = max(0, 64 - voices // 2)
    if first_note + voices > 128:
        first_note = 128 - voices
    notes = range(first_note, first_note + voices)
    for note in notes:
        track.append(Message("note_on", channel=0, note=note, velocity=80, time=0))
    for index, note in enumerate(notes):
        track.append(
            Message(
                "note_off",
                channel=0,
                note=note,
                velocity=0,
                time=HALF * 2 if index == 0 else 0,
            )
        )
    midi.tracks.append(track)
    return midi


def two_piano_split() -> MidiFile:
    midi = _base_midi("two-piano-split", bpm=126)

    piano_a = _named_track("Piano I / Device A")
    piano_a.append(Message("program_change", channel=0, program=0, time=0))
    for note in (60, 64, 67, 72, 67, 64, 60, 55):
        _note(piano_a, note, channel=0, velocity=100, duration=EIGHTH)
    midi.tracks.append(piano_a)

    piano_b = _named_track("Piano II / Device B")
    piano_b.append(Message("program_change", channel=1, program=0, time=0))
    for note in (48, 43, 45, 47, 48, 52, 55, 52):
        _note(piano_b, note, channel=1, velocity=72, duration=EIGHTH)
    midi.tracks.append(piano_b)
    return midi


def sync_click() -> MidiFile:
    midi = _base_midi("sync-click", bpm=120)
    for channel, label in ((0, "Device A"), (1, "Device B")):
        track = _named_track(f"sync-click-{label}")
        for _ in range(16):
            _note(
                track,
                84,
                channel=channel,
                velocity=127,
                duration=60,
                delay=QUARTER - 60 if len(track) > 1 else 0,
            )
        midi.tracks.append(track)
    return midi


def long_run(minutes: int = 120) -> MidiFile:
    if not 1 <= minutes <= 24 * 60:
        raise ValueError("minutes must be between 1 and 1440")
    midi = _base_midi(f"long-run-{minutes}m", bpm=120)
    track = _named_track("long-run")
    total_beats = minutes * 120
    motif = (60, 64, 67, 72, 67, 64, 55, 60)
    for beat in range(total_beats):
        note = motif[beat % len(motif)]
        velocity = 64 + (beat % 4) * 8
        _note(
            track,
            note,
            velocity=velocity,
            duration=EIGHTH,
            delay=0 if beat == 0 else EIGHTH,
        )
    midi.tracks.append(track)
    return midi


def unsupported_events() -> MidiFile:
    midi = _base_midi("unsupported-events")
    track = _named_track("unsupported-events")
    track.append(MetaMessage("text", text="Metadata is data, never executable content.", time=0))
    track.append(MetaMessage("key_signature", key="C", time=0))
    track.append(Message("aftertouch", channel=0, value=40, time=0))
    track.append(Message("pitchwheel", channel=0, pitch=512, time=0))
    track.append(Message("polytouch", channel=0, note=60, value=20, time=0))
    _note(track, 60, velocity=88, duration=QUARTER)
    track.append(Message("pitchwheel", channel=0, pitch=0, time=0))
    midi.tracks.append(track)
    return midi


def _specs(long_run_minutes: int) -> list[tuple[GeneratedFixture, Callable[[], MidiFile]]]:
    specs: list[tuple[GeneratedFixture, Callable[[], MidiFile]]] = [
        (
            GeneratedFixture(
                "single-note",
                "single-note.mid",
                "Minimum host-to-sound-engine Note On/Off path",
                {"channels": [1], "note_range": [60, 60]},
            ),
            single_note,
        ),
        (
            GeneratedFixture(
                "velocity-ladder",
                "velocity-ladder.mid",
                "Audible/observable velocity response",
                {"velocities": [20, 45, 70, 95, 120]},
            ),
            velocity_ladder,
        ),
        (
            GeneratedFixture(
                "sustain-cc64",
                "sustain-cc64.mid",
                "Sustain pedal controller behavior and cleanup",
                {"cc64_values": [127, 0]},
            ),
            sustain_cc64,
        ),
        (
            GeneratedFixture(
                "program-change",
                "program-change.mid",
                "GM Bank Select and Program Change behavior",
                {"programs_zero_based": [0, 33, 48, 56], "bank_msb": 0, "bank_lsb": 0},
            ),
            program_change,
        ),
        (
            GeneratedFixture(
                "gm-ensemble",
                "gm-ensemble.mid",
                "Multitimbral GM playback including channel 10 percussion",
                {"channels_one_based": [1, 2, 3, 4, 5, 10]},
            ),
            gm_ensemble,
        ),
        (
            GeneratedFixture(
                "note-range",
                "note-range.mid",
                "MIDI receive range beyond a physical keybed",
                {"notes": [0, 12, 21, 36, 60, 84, 108, 127]},
            ),
            note_range,
        ),
    ]
    for voices in (16, 32, 48, 64):
        specs.append(
            (
                GeneratedFixture(
                    f"polyphony-{voices}",
                    f"polyphony-{voices}.mid",
                    f"Sustained {voices}-voice polyphony/voice-stealing stress",
                    {"simultaneous_note_ons": voices},
                ),
                lambda voices=voices: polyphony_stress(voices),
            )
        )
    specs.extend(
        [
            (
                GeneratedFixture(
                    "two-piano-split",
                    "two-piano-split.mid",
                    "Two independent piano parts for Device A/Device B routing",
                    {
                        "channels_one_based": [1, 2],
                        "tracks": ["Piano I / Device A", "Piano II / Device B"],
                    },
                ),
                two_piano_split,
            ),
            (
                GeneratedFixture(
                    "sync-click",
                    "sync-click.mid",
                    "Repeated simultaneous events for two-device latency measurement",
                    {"channels_one_based": [1, 2], "clicks_per_channel": 16},
                ),
                sync_click,
            ),
            (
                GeneratedFixture(
                    "long-run",
                    "long-run.mid",
                    "Long deterministic sequence for stability testing",
                    {"minutes": long_run_minutes, "bpm": 120},
                ),
                lambda: long_run(long_run_minutes),
            ),
            (
                GeneratedFixture(
                    "unsupported-events",
                    "unsupported-events.mid",
                    "Parser resilience for metadata and noncritical channel events",
                    {
                        "contains": [
                            "text",
                            "key_signature",
                            "aftertouch",
                            "pitchwheel",
                            "polytouch",
                        ]
                    },
                ),
                unsupported_events,
            ),
        ]
    )
    return specs


def generate_suite(
    output_dir: str | Path,
    *,
    long_run_minutes: int = 120,
) -> list[GeneratedFixture]:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)

    generated: list[GeneratedFixture] = []
    for spec, factory in _specs(long_run_minutes):
        midi = factory()
        midi.save(destination / spec.filename)
        generated.append(spec)

    manifest = {
        "suite": "OpenOrchestrion synthetic MIDI conformance suite",
        "version": 1,
        "ticks_per_beat": TICKS_PER_BEAT,
        "copyright": "Generated test material; no musical repertoire is copied.",
        "fixtures": [asdict(spec) for spec in generated],
    }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return generated


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate copyright-clean MIDI files for OpenOrchestrion conformance testing."
    )
    parser.add_argument(
        "output_dir",
        nargs="?",
        default="build/midi-fixtures",
        help="Destination directory (default: build/midi-fixtures)",
    )
    parser.add_argument(
        "--long-run-minutes",
        type=int,
        default=120,
        help="Logical duration of long-run.mid in minutes (default: 120)",
    )
    args = parser.parse_args()

    generated = generate_suite(args.output_dir, long_run_minutes=args.long_run_minutes)
    print(f"Generated {len(generated)} MIDI fixtures in {Path(args.output_dir).resolve()}")


if __name__ == "__main__":
    main()
