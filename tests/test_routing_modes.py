from __future__ import annotations

from pathlib import Path

import mido
import pytest
from mido import Message, MetaMessage, MidiFile, MidiTrack

from openorchestrion.models import DeviceProfile, PerformanceType
from openorchestrion.playback import RoutingEndpoint, plan_routing
from openorchestrion.playback.timeline import MidiTimeline


def _profile(
    ident: str,
    *,
    polyphony: int,
    preferred_families: tuple[str, ...] = (),
) -> DeviceProfile:
    return DeviceProfile(
        id=ident,
        manufacturer="Test",
        model=ident,
        midi_receive=True,
        transport="usb-midi",
        max_polyphony=polyphony,
        preferred_instrument_families=list(preferred_families),
    )


def _write_piano_parts(path: Path, parts: int, notes_per_part: int = 4) -> MidiTimeline:
    midi = MidiFile(type=1, ticks_per_beat=480)
    tempo = MidiTrack()
    tempo.append(MetaMessage("set_tempo", tempo=mido.bpm2tempo(120), time=0))
    midi.tracks.append(tempo)

    for index in range(parts):
        track = MidiTrack()
        channel = index % 8
        track.append(Message("program_change", channel=channel, program=0, time=0))
        for note_index in range(notes_per_part):
            track.append(
                Message(
                    "note_on",
                    channel=channel,
                    note=48 + index * 4 + note_index,
                    velocity=90,
                    time=0,
                )
            )
        for note_index in range(notes_per_part):
            track.append(
                Message(
                    "note_off",
                    channel=channel,
                    note=48 + index * 4 + note_index,
                    velocity=0,
                    time=480 if note_index == 0 else 0,
                )
            )
        midi.tracks.append(track)
    midi.save(path)
    return MidiTimeline.from_file(path)


@pytest.mark.parametrize(
    "performance_type",
    [
        PerformanceType.TWO_PIANO,
        PerformanceType.PIANO_DUET,
        PerformanceType.DUELING_PIANO,
    ],
)
def test_paired_piano_modes_keep_first_two_parts_on_distinct_outputs(
    tmp_path: Path,
    performance_type: PerformanceType,
) -> None:
    timeline = _write_piano_parts(tmp_path / f"{performance_type.value}.mid", 2)
    endpoints = [
        RoutingEndpoint("A", _profile("a", polyphony=48)),
        RoutingEndpoint("B", _profile("b", polyphony=48)),
    ]

    decision = plan_routing(timeline, endpoints, performance_type=performance_type)
    destinations = {route.destination_device for route in decision.plan.routes}
    assert destinations == {"A", "B"}


def test_multi_instrument_mode_distributes_polyphony_load_by_capacity(tmp_path: Path) -> None:
    timeline = _write_piano_parts(tmp_path / "load.mid", 6, notes_per_part=8)
    endpoints = [
        RoutingEndpoint("small", _profile("small", polyphony=32)),
        RoutingEndpoint("large", _profile("large", polyphony=64)),
    ]

    decision = plan_routing(
        timeline,
        endpoints,
        performance_type=PerformanceType.MULTI_INSTRUMENT,
    )

    assert decision.estimated_peak_load["large"] >= decision.estimated_peak_load["small"]
    small_ratio = decision.estimated_peak_load["small"] / 32
    large_ratio = decision.estimated_peak_load["large"] / 64
    assert abs(small_ratio - large_ratio) <= 0.25


def test_device_and_role_preferences_are_deterministic(tmp_path: Path) -> None:
    timeline = _write_piano_parts(tmp_path / "roles.mid", 2)
    endpoints = [
        RoutingEndpoint("Casio USB", _profile("casio", polyphony=48)),
        RoutingEndpoint("Yamaha USB", _profile("yamaha", polyphony=48)),
    ]

    decision = plan_routing(
        timeline,
        endpoints,
        performance_type=PerformanceType.TWO_PIANO,
        device_preferences=("yamaha", "casio"),
        routing_preferences={"piano_a": "yamaha", "piano_b": "casio"},
    )

    first = min(decision.parts, key=lambda part: part.track_index or -1)
    second = max(decision.parts, key=lambda part: part.track_index or -1)
    assert decision.plan.destinations_for(first.channel, first.track_index)[0].destination_device == "Yamaha USB"
    assert decision.plan.destinations_for(second.channel, second.track_index)[0].destination_device == "Casio USB"


def test_state_only_program_track_drives_note_track_family_affinity(tmp_path: Path) -> None:
    """Program Change is channel state even when notes live on another SMF track."""
    path = tmp_path / "state-track.mid"
    midi = MidiFile(type=1, ticks_per_beat=480)

    tempo = MidiTrack()
    tempo.append(MetaMessage("set_tempo", tempo=mido.bpm2tempo(120), time=0))
    midi.tracks.append(tempo)

    state = MidiTrack()
    state.append(Message("program_change", channel=0, program=40, time=0))  # Violin / strings
    midi.tracks.append(state)

    notes = MidiTrack()
    notes.append(Message("note_on", channel=0, note=67, velocity=90, time=0))
    notes.append(Message("note_off", channel=0, note=67, velocity=0, time=480))
    midi.tracks.append(notes)
    midi.save(path)

    endpoints = [
        RoutingEndpoint(
            "Piano Engine",
            _profile("piano", polyphony=48, preferred_families=("piano",)),
        ),
        RoutingEndpoint(
            "String Engine",
            _profile("strings", polyphony=48, preferred_families=("strings",)),
        ),
    ]

    decision = plan_routing(
        MidiTimeline.from_file(path),
        endpoints,
        performance_type=PerformanceType.MULTI_INSTRUMENT,
    )

    assert len(decision.parts) == 1
    part = decision.parts[0]
    assert part.family == "strings"
    route = decision.plan.destinations_for(part.channel, part.track_index)[0]
    assert route.destination_device == "String Engine"
