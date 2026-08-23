from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import mido
import pytest
from mido import Message, MetaMessage, MidiFile, MidiTrack

from openorchestrion.midi.router import MidiRoute, RoutingPlan
from openorchestrion.models import DeviceProfile, PerformanceType
from openorchestrion.playback import (
    ManualClock,
    MidiOutputRouter,
    PlaybackEngine,
    PlaybackOutputError,
    QueueItemSpec,
    RoutingEndpoint,
    VirtualMidiOutput,
    plan_routing,
)
from openorchestrion.playback.timeline import MidiTimeline


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
        self.events.append(("failed", play_id, played_seconds, error))


def _profile(
    ident: str,
    *,
    families: tuple[str, ...] = (),
    polyphony: int = 48,
    latency_ms: float = 0.0,
) -> DeviceProfile:
    return DeviceProfile(
        id=ident,
        manufacturer="Test",
        model=ident,
        midi_receive=True,
        transport="usb-midi",
        max_polyphony=polyphony,
        latency_offset_ms=latency_ms,
        preferred_instrument_families=list(families),
    )


def _write_two_piano_same_channel(path: Path) -> float:
    midi = MidiFile(type=1, ticks_per_beat=480)
    tempo = MidiTrack()
    tempo.append(MetaMessage("set_tempo", tempo=mido.bpm2tempo(120), time=0))
    midi.tracks.append(tempo)

    first = MidiTrack()
    first.append(Message("program_change", channel=0, program=0, time=0))
    first.append(Message("note_on", channel=0, note=60, velocity=90, time=0))
    first.append(Message("note_off", channel=0, note=60, velocity=0, time=480))
    midi.tracks.append(first)

    second = MidiTrack()
    second.append(Message("program_change", channel=0, program=0, time=0))
    second.append(Message("note_on", channel=0, note=72, velocity=90, time=0))
    second.append(Message("note_off", channel=0, note=72, velocity=0, time=480))
    midi.tracks.append(second)
    midi.save(path)
    return MidiFile(path).length


def _write_ensemble(path: Path) -> MidiTimeline:
    midi = MidiFile(type=1, ticks_per_beat=480)
    tempo = MidiTrack()
    tempo.append(MetaMessage("set_tempo", tempo=mido.bpm2tempo(120), time=0))
    midi.tracks.append(tempo)

    bass = MidiTrack()
    bass.append(Message("program_change", channel=1, program=32, time=0))
    bass.append(Message("note_on", channel=1, note=40, velocity=90, time=0))
    bass.append(Message("note_off", channel=1, note=40, velocity=0, time=480))
    midi.tracks.append(bass)

    strings = MidiTrack()
    strings.append(Message("program_change", channel=2, program=48, time=0))
    strings.append(Message("note_on", channel=2, note=67, velocity=90, time=0))
    strings.append(Message("note_off", channel=2, note=67, velocity=0, time=480))
    midi.tracks.append(strings)
    midi.save(path)
    return MidiTimeline.from_file(path)


def test_timeline_preserves_track_identity_for_same_channel(tmp_path: Path) -> None:
    path = tmp_path / "same-channel.mid"
    _write_two_piano_same_channel(path)
    timeline = MidiTimeline.from_file(path)
    notes = [event for event in timeline.events if event.message.type == "note_on"]

    assert [(event.track_index, event.message.channel, event.message.note) for event in notes] == [
        (1, 0, 60),
        (2, 0, 72),
    ]


def test_two_piano_plan_separates_tracks_and_applies_latency(tmp_path: Path) -> None:
    path = tmp_path / "two-piano.mid"
    _write_two_piano_same_channel(path)
    timeline = MidiTimeline.from_file(path)
    endpoints = [
        RoutingEndpoint("A", _profile("a", latency_ms=2.8)),
        RoutingEndpoint("B", _profile("b", latency_ms=0.0)),
    ]

    decision = plan_routing(
        timeline,
        endpoints,
        performance_type=PerformanceType.TWO_PIANO,
    )

    first = decision.plan.destinations_for(0, 1)
    second = decision.plan.destinations_for(0, 2)
    assert {first[0].destination_device, second[0].destination_device} == {"A", "B"}
    delays = {
        route.destination_device: route.latency_offset_ms for route in decision.plan.routes
    }
    assert delays == {"A": pytest.approx(2.8), "B": pytest.approx(0.0)}


def test_instrument_family_preferences_win_before_load_balance(tmp_path: Path) -> None:
    timeline = _write_ensemble(tmp_path / "ensemble.mid")
    endpoints = [
        RoutingEndpoint("strings-engine", _profile("strings", families=("strings",))),
        RoutingEndpoint("bass-engine", _profile("bass", families=("bass",))),
    ]
    decision = plan_routing(
        timeline,
        endpoints,
        performance_type=PerformanceType.MULTI_INSTRUMENT,
    )

    bass_route = decision.plan.destinations_for(1, 1)[0]
    strings_route = decision.plan.destinations_for(2, 2)[0]
    assert bass_route.destination_device == "bass-engine"
    assert strings_route.destination_device == "strings-engine"


def test_explicit_routes_can_broadcast_one_part() -> None:
    clock = ManualClock()
    output_a = VirtualMidiOutput("A", clock)
    output_b = VirtualMidiOutput("B", clock)
    router = MidiOutputRouter([output_a, output_b], default_device="A")
    plan = RoutingPlan(
        [
            MidiRoute(source_channel=0, destination_device="A"),
            MidiRoute(source_channel=0, destination_device="B"),
        ]
    )

    routed = router.route_messages(Message("note_on", channel=0, note=60, velocity=90), plan=plan)
    assert {item.destination_device for item in routed} == {"A", "B"}


@pytest.mark.asyncio
async def test_engine_auto_routes_two_piano_tracks_from_one_master_timeline(
    tmp_path: Path,
) -> None:
    path = tmp_path / "two-piano.mid"
    duration = _write_two_piano_same_channel(path)
    clock = ManualClock()
    output_a = VirtualMidiOutput("A", clock, profile=_profile("a"))
    output_b = VirtualMidiOutput("B", clock, profile=_profile("b"))
    engine = PlaybackEngine(
        router=MidiOutputRouter([output_a, output_b], default_device="A"),
        history=FakeHistory(),
        clock=clock,
    )
    await engine.set_queue(
        [
            QueueItemSpec(
                "duet",
                "Duet",
                duration,
                str(path),
                performance_type="TWO_PIANO",
            )
        ]
    )
    await engine.transport("play")
    await clock.advance(duration + 0.05)

    notes_a = [event.message.note for event in output_a.sent if event.message.type == "note_on"]
    notes_b = [event.message.note for event in output_b.sent if event.message.type == "note_on"]
    assert {tuple(notes_a), tuple(notes_b)} == {(60,), (72,)}
    assert engine.last_routing_decision is not None


class FailingOutput(VirtualMidiOutput):
    async def send(self, message: Message) -> None:
        if message.type == "note_on":
            raise PlaybackOutputError("simulated unplug")
        await super().send(message)


@pytest.mark.asyncio
async def test_destination_failure_stops_and_panics_remaining_output(tmp_path: Path) -> None:
    path = tmp_path / "two-piano.mid"
    duration = _write_two_piano_same_channel(path)
    clock = ManualClock()
    failed = FailingOutput("A", clock)
    survivor = VirtualMidiOutput("B", clock)
    history = FakeHistory()
    engine = PlaybackEngine(
        router=MidiOutputRouter([failed, survivor], default_device="A"),
        history=history,
        clock=clock,
    )
    plan = RoutingPlan(
        [
            MidiRoute(source_channel=0, source_track=1, destination_device="A"),
            MidiRoute(source_channel=0, source_track=2, destination_device="B"),
        ]
    )
    await engine.set_queue(
        [QueueItemSpec("duet", "Duet", duration, str(path), routing_plan=plan)]
    )
    await engine.transport("play")
    await clock.advance(0.01)

    assert (await engine.playback_snapshot()).state == "stopped"
    assert any(event[0] == "failed" for event in history.events)
    assert any(
        event.message.type == "control_change" and event.message.control == 123
        for event in survivor.sent
    )
