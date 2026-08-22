from __future__ import annotations

import json
from pathlib import Path

from mido import MidiFile

from openorchestrion.testing.midi_fixtures import generate_suite


def _messages(path: Path, message_type: str):
    midi = MidiFile(path)
    return [
        message
        for track in midi.tracks
        for message in track
        if message.type == message_type
    ]


def test_generate_suite_creates_expected_files(tmp_path: Path) -> None:
    generated = generate_suite(tmp_path, long_run_minutes=1)

    expected = {
        "single-note.mid",
        "velocity-ladder.mid",
        "sustain-cc64.mid",
        "program-change.mid",
        "gm-ensemble.mid",
        "note-range.mid",
        "polyphony-16.mid",
        "polyphony-32.mid",
        "polyphony-48.mid",
        "polyphony-64.mid",
        "two-piano-split.mid",
        "sync-click.mid",
        "long-run.mid",
        "unsupported-events.mid",
    }

    assert {fixture.filename for fixture in generated} == expected
    assert expected <= {path.name for path in tmp_path.glob("*.mid")}

    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["suite"] == "OpenOrchestrion synthetic MIDI conformance suite"
    assert len(manifest["fixtures"]) == len(expected)


def test_velocity_ladder_has_known_velocities(tmp_path: Path) -> None:
    generate_suite(tmp_path, long_run_minutes=1)
    velocities = [
        message.velocity
        for message in _messages(tmp_path / "velocity-ladder.mid", "note_on")
        if message.velocity > 0
    ]
    assert velocities == [20, 45, 70, 95, 120]


def test_sustain_fixture_has_pedal_down_and_up(tmp_path: Path) -> None:
    generate_suite(tmp_path, long_run_minutes=1)
    cc64 = [
        message.value
        for message in _messages(tmp_path / "sustain-cc64.mid", "control_change")
        if message.control == 64
    ]
    assert cc64 == [127, 0]


def test_gm_ensemble_uses_expected_channels_and_percussion(tmp_path: Path) -> None:
    generate_suite(tmp_path, long_run_minutes=1)
    midi = MidiFile(tmp_path / "gm-ensemble.mid")
    channels = {
        message.channel
        for track in midi.tracks
        for message in track
        if hasattr(message, "channel")
    }
    assert channels == {0, 1, 2, 3, 4, 9}

    drum_notes = [
        message.note
        for track in midi.tracks
        for message in track
        if message.type == "note_on" and message.channel == 9 and message.velocity > 0
    ]
    assert drum_notes
    assert {36, 38, 42} <= set(drum_notes)


def test_note_range_reaches_full_midi_range(tmp_path: Path) -> None:
    generate_suite(tmp_path, long_run_minutes=1)
    notes = [
        message.note
        for message in _messages(tmp_path / "note-range.mid", "note_on")
        if message.velocity > 0
    ]
    assert min(notes) == 0
    assert max(notes) == 127


def test_polyphony_fixtures_start_expected_number_of_notes_together(tmp_path: Path) -> None:
    generate_suite(tmp_path, long_run_minutes=1)
    for voices in (16, 32, 48, 64):
        midi = MidiFile(tmp_path / f"polyphony-{voices}.mid")
        note_ons = [
            message
            for track in midi.tracks
            for message in track
            if message.type == "note_on" and message.velocity > 0
        ]
        assert len(note_ons) == voices
        assert all(message.time == 0 for message in note_ons)


def test_two_piano_fixture_separates_parts_by_channel(tmp_path: Path) -> None:
    generate_suite(tmp_path, long_run_minutes=1)
    midi = MidiFile(tmp_path / "two-piano-split.mid")

    by_track = []
    for track in midi.tracks:
        channels = {
            message.channel
            for message in track
            if message.type == "note_on" and message.velocity > 0
        }
        if channels:
            by_track.append(channels)

    assert {frozenset(channels) for channels in by_track} == {
        frozenset({0}),
        frozenset({1}),
    }


def test_sync_click_has_matching_note_on_timestamps(tmp_path: Path) -> None:
    generate_suite(tmp_path, long_run_minutes=1)
    midi = MidiFile(tmp_path / "sync-click.mid")

    absolute_by_channel: dict[int, list[int]] = {0: [], 1: []}
    for track in midi.tracks:
        absolute = 0
        for message in track:
            absolute += message.time
            if (
                message.type == "note_on"
                and message.velocity > 0
                and message.channel in absolute_by_channel
            ):
                absolute_by_channel[message.channel].append(absolute)

    assert len(absolute_by_channel[0]) == 16
    assert absolute_by_channel[0] == absolute_by_channel[1]


def test_unsupported_events_fixture_is_still_parseable(tmp_path: Path) -> None:
    generate_suite(tmp_path, long_run_minutes=1)
    midi = MidiFile(tmp_path / "unsupported-events.mid")
    types = {message.type for track in midi.tracks for message in track}
    assert {"text", "key_signature", "aftertouch", "pitchwheel", "polytouch", "note_on"} <= types
