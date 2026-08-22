from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import mido
import pytest
from mido import Message, MetaMessage, MidiFile, MidiTrack

from openorchestrion.midi.router import MidiRoute, RoutingPlan
from openorchestrion.playback import (
    ManualClock,
    MidiOutputRouter,
    PlaybackEngine,
    QueueItemSpec,
    VirtualMidiOutput,
)


@dataclass
class FakeHistory:
    events: list[tuple] = field(default_factory=list)
    counter: int = 0

    async def queued(
        self,
        *,
        asset_id: str,
        composition_id: str | None,
        duration_seconds: float,
    ) -> str:
        self.counter += 1
        play_id = f"p{self.counter}"
        self.events.append(("queued", play_id, asset_id, composition_id, duration_seconds))
        return play_id

    async def started(self, play_id: str) -> None:
        self.events.append(("started", play_id))

    async def progress(self, play_id: str, played_seconds: float) -> None:
        self.events.append(("progress", play_id, round(played_seconds, 3)))

    async def completed(self, play_id: str, played_seconds: float) -> None:
        self.events.append(("completed", play_id, round(played_seconds, 3)))

    async def skipped(self, play_id: str, played_seconds: float) -> None:
        self.events.append(("skipped", play_id, round(played_seconds, 3)))

    async def failed(self, play_id: str, played_seconds: float, error: str) -> None:
        self.events.append(("failed", play_id, round(played_seconds, 3), error))


def _write_midi(
    path: Path,
    *,
    channels: tuple[int, ...] = (0,),
    beats: int = 4,
    bpm: int = 120,
) -> float:
    midi = MidiFile(type=1, ticks_per_beat=480)
    meta = MidiTrack()
    meta.append(MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm), time=0))
    midi.tracks.append(meta)
    for channel in channels:
        track = MidiTrack()
        track.append(Message("program_change", channel=channel, program=0, time=0))
        for index in range(beats):
            note = 60 + channel * 12 + index
            track.append(Message("note_on", channel=channel, note=note, velocity=90, time=0))
            track.append(Message("note_off", channel=channel, note=note, velocity=0, time=480))
        midi.tracks.append(track)
    midi.save(path)
    return MidiFile(path).length


async def _engine(*, two_outputs: bool = False):
    clock = ManualClock()
    output_a = VirtualMidiOutput("A", clock)
    outputs = [output_a]
    output_b = None
    if two_outputs:
        output_b = VirtualMidiOutput("B", clock)
        outputs.append(output_b)
    router = MidiOutputRouter(outputs, default_device="A")
    history = FakeHistory()
    engine = PlaybackEngine(router=router, history=history, clock=clock)
    return engine, clock, history, output_a, output_b


@pytest.mark.asyncio
async def test_virtual_output_plays_a_midi_file(tmp_path: Path) -> None:
    midi = tmp_path / "one.mid"
    duration = _write_midi(midi, beats=1)
    engine, clock, history, output, _ = await _engine()
    await engine.set_queue([QueueItemSpec("asset1", "One", duration, str(midi))])
    await engine.transport("play")
    await clock.advance(duration + 0.01)

    assert (await engine.playback_snapshot()).state == "stopped"
    message_types = [event.message.type for event in output.sent]
    assert "note_on" in message_types
    assert "note_off" in message_types
    assert any(event[0] == "completed" for event in history.events)


@pytest.mark.asyncio
async def test_pause_resume_preserves_timeline_position(tmp_path: Path) -> None:
    midi = tmp_path / "long.mid"
    duration = _write_midi(midi, beats=8)
    engine, clock, _, _, _ = await _engine()
    await engine.set_queue([QueueItemSpec("asset1", "Long", duration, str(midi))])
    await engine.transport("play")
    await clock.advance(1.2)

    paused = await engine.transport("pause")
    assert paused.state == "paused"
    paused_position = paused.position.position_ms
    await clock.advance(5)
    assert (await engine.playback_snapshot()).position.position_ms == paused_position

    resumed = await engine.transport("play")
    assert resumed.state == "playing"
    assert abs(resumed.position.position_ms - paused_position) <= 1
    await clock.advance(duration)
    assert (await engine.playback_snapshot()).state == "stopped"


@pytest.mark.asyncio
async def test_skip_marks_history_and_starts_next(tmp_path: Path) -> None:
    first = tmp_path / "first.mid"
    second = tmp_path / "second.mid"
    first_duration = _write_midi(first, beats=8)
    second_duration = _write_midi(second, beats=2)
    engine, clock, history, _, _ = await _engine()
    await engine.set_queue(
        [
            QueueItemSpec("first", "First", first_duration, str(first)),
            QueueItemSpec("second", "Second", second_duration, str(second)),
        ]
    )
    await engine.transport("play")
    await clock.advance(0.6)
    state = await engine.transport("skip")

    assert state.state == "playing"
    assert state.now_playing.asset_id == "second"
    assert any(event[0] == "skipped" and event[1] == "p1" for event in history.events)
    assert any(event[0] == "started" and event[1] == "p2" for event in history.events)


@pytest.mark.asyncio
async def test_completion_advances_automatically(tmp_path: Path) -> None:
    first = tmp_path / "first.mid"
    second = tmp_path / "second.mid"
    first_duration = _write_midi(first, beats=1)
    second_duration = _write_midi(second, beats=1)
    engine, clock, history, _, _ = await _engine()
    await engine.set_queue(
        [
            QueueItemSpec("first", "First", first_duration, str(first)),
            QueueItemSpec("second", "Second", second_duration, str(second)),
        ]
    )
    await engine.transport("play")
    await clock.advance(first_duration + 0.01)

    state = await engine.playback_snapshot()
    assert state.state == "playing"
    assert state.now_playing.asset_id == "second"
    assert any(event[0] == "completed" and event[1] == "p1" for event in history.events)

    await clock.advance(second_duration + 0.01)
    assert (await engine.playback_snapshot()).state == "stopped"


@pytest.mark.asyncio
async def test_stop_and_panic_cleanup_every_output(tmp_path: Path) -> None:
    midi = tmp_path / "two.mid"
    duration = _write_midi(midi, channels=(0, 1), beats=4)
    engine, clock, _, output_a, output_b = await _engine(two_outputs=True)
    assert output_b is not None
    plan = RoutingPlan([MidiRoute(0, "A"), MidiRoute(1, "B")])
    await engine.set_queue(
        [QueueItemSpec("two", "Two", duration, str(midi), routing_plan=plan)]
    )
    await engine.transport("play")
    await clock.advance(0.2)
    await engine.transport("stop")

    for output in (output_a, output_b):
        assert any(
            event.message.type == "control_change" and event.message.control == 123
            for event in output.sent
        )

    before_a = len(output_a.sent)
    before_b = len(output_b.sent)
    await engine.transport("panic")
    assert len(output_a.sent) > before_a
    assert len(output_b.sent) > before_b


@pytest.mark.asyncio
async def test_two_piano_routes_from_one_master_timeline(tmp_path: Path) -> None:
    midi = tmp_path / "two-piano.mid"
    duration = _write_midi(midi, channels=(0, 1), beats=2)
    engine, clock, _, output_a, output_b = await _engine(two_outputs=True)
    assert output_b is not None
    plan = RoutingPlan(
        [
            MidiRoute(source_channel=0, destination_device="A"),
            MidiRoute(source_channel=1, destination_device="B"),
        ]
    )
    await engine.set_queue(
        [QueueItemSpec("duet", "Duet", duration, str(midi), routing_plan=plan)]
    )
    await engine.transport("play")
    await clock.advance(duration + 0.01)

    channels_a = {
        event.message.channel for event in output_a.sent if event.message.type == "note_on"
    }
    channels_b = {
        event.message.channel for event in output_b.sent if event.message.type == "note_on"
    }
    assert channels_a == {0}
    assert channels_b == {1}
    first_a = next(event.at_seconds for event in output_a.sent if event.message.type == "note_on")
    first_b = next(event.at_seconds for event in output_b.sent if event.message.type == "note_on")
    assert first_a == first_b


@pytest.mark.asyncio
async def test_missing_file_records_failure(tmp_path: Path) -> None:
    engine, _, history, _, _ = await _engine()
    await engine.set_queue(
        [QueueItemSpec("missing", "Missing", 10.0, str(tmp_path / "missing.mid"))]
    )
    with pytest.raises(Exception):
        await engine.transport("play")
    assert any(event[0] == "failed" for event in history.events)
    assert (await engine.playback_snapshot()).state == "stopped"


@pytest.mark.asyncio
async def test_command_ids_are_idempotent(tmp_path: Path) -> None:
    midi = tmp_path / "idempotent.mid"
    duration = _write_midi(midi, beats=4)
    engine, clock, history, _, _ = await _engine()
    await engine.set_queue([QueueItemSpec("asset", "Asset", duration, str(midi))])
    await engine.transport("play", command_id="play-1")
    await clock.advance(0.3)
    first = await engine.transport("skip", command_id="skip-1")
    second = await engine.transport("skip", command_id="skip-1")

    assert first.state == second.state == "stopped"
    assert sum(1 for event in history.events if event[0] == "skipped") == 1
