from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest
from mido import MidiFile

from openorchestrion.midi.router import MidiRoute, RoutingPlan
from openorchestrion.playback import (
    ManualClock,
    MidiOutputRouter,
    PlaybackEngine,
    QueueItemSpec,
    VirtualMidiOutput,
)
from openorchestrion.testing.midi_fixtures import generate_suite


@dataclass
class FixtureHistory:
    events: list[tuple] = field(default_factory=list)
    counter: int = 0

    async def queued(self, *, asset_id: str, composition_id: str | None, duration_seconds: float) -> str:
        self.counter += 1
        play_id = f"fixture-{self.counter}"
        self.events.append(("queued", play_id, asset_id))
        return play_id

    async def started(self, play_id: str) -> None:
        self.events.append(("started", play_id))

    async def progress(self, play_id: str, played_seconds: float) -> None:
        self.events.append(("progress", play_id, played_seconds))

    async def completed(self, play_id: str, played_seconds: float) -> None:
        self.events.append(("completed", play_id, played_seconds))

    async def skipped(self, play_id: str, played_seconds: float) -> None:
        self.events.append(("skipped", play_id, played_seconds))

    async def failed(self, play_id: str, played_seconds: float, error: str) -> None:
        self.events.append(("failed", play_id, error))


@pytest.mark.asyncio
async def test_generated_single_note_fixture_reaches_virtual_output(tmp_path: Path) -> None:
    fixture_dir = tmp_path / "fixtures"
    generate_suite(fixture_dir, long_run_minutes=1)
    midi_path = fixture_dir / "single-note.mid"
    duration = MidiFile(midi_path).length
    clock = ManualClock()
    output = VirtualMidiOutput("virtual", clock)
    history = FixtureHistory()
    engine = PlaybackEngine(
        router=MidiOutputRouter([output], default_device="virtual"),
        history=history,
        clock=clock,
    )
    await engine.set_queue(
        [QueueItemSpec("single-note", "Single Note", duration, str(midi_path))]
    )
    await engine.transport("play")
    await clock.advance(duration + 0.01)

    assert any(event.message.type == "note_on" for event in output.sent)
    assert any(event.message.type == "note_off" for event in output.sent)
    assert any(event[0] == "completed" for event in history.events)


@pytest.mark.asyncio
async def test_generated_two_piano_fixture_uses_two_virtual_destinations(tmp_path: Path) -> None:
    fixture_dir = tmp_path / "fixtures"
    generate_suite(fixture_dir, long_run_minutes=1)
    midi_path = fixture_dir / "two-piano-split.mid"
    duration = MidiFile(midi_path).length
    clock = ManualClock()
    output_a = VirtualMidiOutput("piano-a", clock)
    output_b = VirtualMidiOutput("piano-b", clock)
    history = FixtureHistory()
    engine = PlaybackEngine(
        router=MidiOutputRouter([output_a, output_b], default_device="piano-a"),
        history=history,
        clock=clock,
    )
    routing = RoutingPlan(
        [
            MidiRoute(source_channel=0, destination_device="piano-a"),
            MidiRoute(source_channel=1, destination_device="piano-b"),
        ]
    )
    await engine.set_queue(
        [
            QueueItemSpec(
                "two-piano-split",
                "Two Piano Split",
                duration,
                str(midi_path),
                routing_plan=routing,
            )
        ]
    )
    await engine.transport("play")
    await clock.advance(duration + 0.01)

    notes_a = [event for event in output_a.sent if event.message.type == "note_on"]
    notes_b = [event for event in output_b.sent if event.message.type == "note_on"]
    assert notes_a and notes_b
    assert {event.message.channel for event in notes_a} == {0}
    assert {event.message.channel for event in notes_b} == {1}
    assert notes_a[0].at_seconds == notes_b[0].at_seconds
