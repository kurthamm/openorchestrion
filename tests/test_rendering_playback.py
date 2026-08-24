from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

import mido
import pytest
from mido import Message, MetaMessage, MidiFile, MidiTrack

from openorchestrion.models import DeviceProfile, PerformanceType
from openorchestrion.playback import (
    ManualClock,
    MidiOutputRouter,
    PlaybackEngine,
    QueueItemSpec,
    VirtualMidiOutput,
)
from openorchestrion.playback.rendering import (
    ProgramOverride,
    RenderingMode,
    RenderingPolicy,
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


def _profile(name: str, family: str) -> DeviceProfile:
    return DeviceProfile(
        id=name.casefold(),
        manufacturer="Test",
        model=name,
        midi_receive=True,
        transport="usb-midi",
        max_polyphony=48,
        preferred_instrument_families=[family],
    )


def _write_arrangement(path: Path) -> float:
    """Strings + violin + drums, with useful controller state for rendering tests."""
    midi = MidiFile(type=1, ticks_per_beat=480)
    tempo = MidiTrack()
    tempo.append(MetaMessage("set_tempo", tempo=mido.bpm2tempo(120), time=0))
    midi.tracks.append(tempo)

    strings = MidiTrack()
    strings.append(Message("control_change", channel=0, control=0, value=1, time=0))
    strings.append(Message("program_change", channel=0, program=48, time=0))
    strings.append(Message("control_change", channel=0, control=64, value=127, time=0))
    strings.append(Message("note_on", channel=0, note=60, velocity=91, time=0))
    strings.append(Message("note_off", channel=0, note=60, velocity=0, time=480))
    strings.append(Message("control_change", channel=0, control=64, value=0, time=0))
    midi.tracks.append(strings)

    violin = MidiTrack()
    violin.append(Message("program_change", channel=1, program=40, time=0))
    violin.append(Message("note_on", channel=1, note=67, velocity=73, time=0))
    violin.append(Message("note_off", channel=1, note=67, velocity=0, time=480))
    midi.tracks.append(violin)

    drums = MidiTrack()
    drums.append(Message("note_on", channel=9, note=36, velocity=110, time=0))
    drums.append(Message("note_off", channel=9, note=36, velocity=0, time=480))
    midi.tracks.append(drums)

    midi.save(path)
    return MidiFile(path).length


def _write_resume_piece(path: Path) -> float:
    midi = MidiFile(type=1, ticks_per_beat=480)
    tempo = MidiTrack()
    tempo.append(MetaMessage("set_tempo", tempo=mido.bpm2tempo(120), time=0))
    midi.tracks.append(tempo)

    track = MidiTrack()
    track.append(Message("program_change", channel=0, program=48, time=0))
    track.append(Message("control_change", channel=0, control=64, value=127, time=0))
    track.append(Message("note_on", channel=0, note=60, velocity=80, time=0))
    track.append(Message("note_off", channel=0, note=60, velocity=0, time=480))
    # A half-second gap leaves a clean pause point after the first note.
    track.append(Message("note_on", channel=0, note=62, velocity=82, time=480))
    track.append(Message("note_off", channel=0, note=62, velocity=0, time=480))
    track.append(Message("control_change", channel=0, control=64, value=0, time=0))
    midi.tracks.append(track)
    midi.save(path)
    return MidiFile(path).length


async def _single_output_engine():
    clock = ManualClock()
    output = VirtualMidiOutput("A", clock)
    history = FakeHistory()
    engine = PlaybackEngine(
        router=MidiOutputRouter([output], default_device="A"),
        history=history,
        clock=clock,
    )
    return engine, clock, history, output


def _programs(output: VirtualMidiOutput, channel: int) -> list[int]:
    return [
        int(event.message.program)
        for event in output.sent
        if event.message.type == "program_change" and event.message.channel == channel
    ]


@pytest.mark.asyncio
async def test_default_runtime_preserves_original_arrangement(tmp_path: Path) -> None:
    midi = tmp_path / "original.mid"
    duration = _write_arrangement(midi)
    engine, clock, history, output = await _single_output_engine()

    await engine.set_queue([QueueItemSpec("asset", "Original", duration, str(midi))])
    await engine.transport("play")
    await clock.advance(duration + 0.01)

    assert _programs(output, 0) == [48]
    assert _programs(output, 1) == [40]
    assert any(
        event.message.type == "control_change"
        and event.message.channel == 0
        and event.message.control == 0
        for event in output.sent
    )
    assert any(
        event.message.type == "note_on" and event.message.channel == 9
        for event in output.sent
    )
    assert any(event[0] == "completed" for event in history.events)


@pytest.mark.asyncio
async def test_piano_only_policy_is_heard_by_the_output(tmp_path: Path) -> None:
    midi = tmp_path / "piano-only.mid"
    duration = _write_arrangement(midi)
    engine, clock, _, output = await _single_output_engine()

    await engine.set_queue(
        [
            QueueItemSpec(
                "asset",
                "Piano Only",
                duration,
                str(midi),
                rendering_policy=RenderingPolicy(mode=RenderingMode.PIANO_ONLY),
            )
        ]
    )
    await engine.transport("play")
    await clock.advance(duration + 0.01)

    assert _programs(output, 0) == [0]
    assert _programs(output, 1) == [0]
    assert not any(
        event.message.type == "note_on" and event.message.channel == 9
        for event in output.sent
    )
    assert not any(
        event.message.type == "control_change"
        and event.message.channel == 0
        and event.message.control in {0, 32}
        for event in output.sent
    )
    assert any(
        event.message.type == "note_on"
        and event.message.channel == 0
        and event.message.note == 60
        and event.message.velocity == 91
        for event in output.sent
    )
    assert any(
        event.message.type == "control_change"
        and event.message.channel == 0
        and event.message.control == 64
        and event.message.value == 127
        for event in output.sent
    )


@pytest.mark.asyncio
async def test_override_runtime_changes_only_target_channel(tmp_path: Path) -> None:
    midi = tmp_path / "override.mid"
    duration = _write_arrangement(midi)
    engine, clock, _, output = await _single_output_engine()

    await engine.set_queue(
        [
            QueueItemSpec(
                "asset",
                "Override",
                duration,
                str(midi),
                rendering_policy=RenderingPolicy(
                    mode=RenderingMode.OVERRIDE,
                    program_overrides=(ProgramOverride(channel=0, program=24),),
                ),
            )
        ]
    )
    await engine.transport("play")
    await clock.advance(duration + 0.01)

    assert _programs(output, 0) == [24]
    assert _programs(output, 1) == [40]
    assert any(
        event.message.type == "note_on" and event.message.channel == 9
        for event in output.sent
    )


@pytest.mark.asyncio
async def test_routing_plans_from_rendered_program_family(tmp_path: Path) -> None:
    midi = tmp_path / "render-before-route.mid"
    source = MidiFile(type=1, ticks_per_beat=480)
    tempo = MidiTrack()
    tempo.append(MetaMessage("set_tempo", tempo=mido.bpm2tempo(120), time=0))
    source.tracks.append(tempo)
    track = MidiTrack()
    track.append(Message("program_change", channel=0, program=40, time=0))  # strings
    track.append(Message("note_on", channel=0, note=67, velocity=90, time=0))
    track.append(Message("note_off", channel=0, note=67, velocity=0, time=480))
    source.tracks.append(track)
    source.save(midi)
    duration = MidiFile(midi).length

    clock = ManualClock()
    strings = VirtualMidiOutput("Strings", clock, profile=_profile("Strings", "strings"))
    piano = VirtualMidiOutput("Piano", clock, profile=_profile("Piano", "piano"))
    engine = PlaybackEngine(
        router=MidiOutputRouter([strings, piano], default_device="Strings"),
        history=FakeHistory(),
        clock=clock,
    )

    await engine.set_queue(
        [
            QueueItemSpec(
                "asset",
                "Rendered Routing",
                duration,
                str(midi),
                performance_type=PerformanceType.MULTI_INSTRUMENT.value,
                rendering_policy=RenderingPolicy(mode=RenderingMode.PIANO_ONLY),
            )
        ]
    )
    await engine.transport("play")

    decision = engine.last_routing_decision
    assert decision is not None
    assert len(decision.parts) == 1
    part = decision.parts[0]
    assert part.family == "piano"
    route = decision.plan.destinations_for(part.channel, part.track_index)[0]
    assert route.destination_device == "Piano"

    await clock.advance(duration + 0.01)
    assert any(event.message.type == "note_on" for event in piano.sent)
    assert not any(event.message.type == "note_on" for event in strings.sent)


@pytest.mark.asyncio
async def test_resume_primes_rendered_program_not_source_program(tmp_path: Path) -> None:
    midi = tmp_path / "resume.mid"
    duration = _write_resume_piece(midi)
    engine, clock, _, output = await _single_output_engine()

    await engine.set_queue(
        [
            QueueItemSpec(
                "asset",
                "Resume",
                duration,
                str(midi),
                rendering_policy=RenderingPolicy(mode=RenderingMode.PIANO_ONLY),
            )
        ]
    )
    await engine.transport("play")
    await clock.advance(0.6)
    await engine.transport("pause")
    before_resume = len(output.sent)

    await engine.transport("play")
    # The worker sends priming state before waiting for the next musical event.
    for _ in range(5):
        await asyncio.sleep(0)

    resumed = output.sent[before_resume:]
    assert any(
        event.message.type == "program_change"
        and event.message.channel == 0
        and event.message.program == 0
        for event in resumed
    )
    assert not any(
        event.message.type == "program_change"
        and event.message.channel == 0
        and event.message.program == 48
        for event in resumed
    )

    await clock.advance(duration)
    assert (await engine.playback_snapshot()).state == "stopped"
