from __future__ import annotations

from pathlib import Path

import pytest
from mido import Message, MidiFile, MidiTrack

from openorchestrion.midi.router import MidiRoute, RoutingPlan
from openorchestrion.playback import ManualClock, MidiOutputRouter, VirtualMidiOutput
from openorchestrion.playback.timeline import MidiTimeline


def test_state_only_track_fans_channel_state_to_track_specific_routes() -> None:
    clock = ManualClock()
    router = MidiOutputRouter(
        [VirtualMidiOutput("A", clock), VirtualMidiOutput("B", clock)],
        default_device="A",
    )
    plan = RoutingPlan(
        [
            MidiRoute(source_channel=0, source_track=1, destination_device="A"),
            MidiRoute(source_channel=0, source_track=2, destination_device="B"),
        ]
    )

    routed = router.route_messages(
        Message("program_change", channel=0, program=0),
        track_index=0,
        plan=plan,
    )
    assert {event.destination_device for event in routed} == {"A", "B"}


def test_type_two_midi_is_rejected_as_not_one_master_timeline(tmp_path: Path) -> None:
    path = tmp_path / "asynchronous.mid"
    midi = MidiFile(type=2, ticks_per_beat=480)
    first = MidiTrack()
    first.append(Message("note_on", channel=0, note=60, velocity=90, time=0))
    first.append(Message("note_off", channel=0, note=60, velocity=0, time=480))
    second = MidiTrack()
    second.append(Message("note_on", channel=1, note=72, velocity=90, time=0))
    second.append(Message("note_off", channel=1, note=72, velocity=0, time=960))
    midi.tracks.extend([first, second])
    midi.save(path)

    with pytest.raises(ValueError, match="asynchronous tracks"):
        MidiTimeline.from_file(path)
