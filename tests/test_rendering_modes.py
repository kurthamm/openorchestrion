from __future__ import annotations

import pytest
from mido import Message

from openorchestrion.playback.rendering import (
    ProgramOverride,
    RenderingError,
    RenderingMode,
    RenderingPolicy,
    render_timeline,
)
from openorchestrion.playback.timeline import MidiTimeline, MidiTimelineEvent


def _event(at: float, message: Message, track: int) -> MidiTimelineEvent:
    return MidiTimelineEvent(at_seconds=at, message=message, track_index=track)


def _sample_timeline() -> MidiTimeline:
    return MidiTimeline(
        events=(
            _event(0.0, Message("control_change", channel=0, control=0, value=1), 0),
            _event(0.0, Message("program_change", channel=0, program=48), 0),
            _event(0.1, Message("control_change", channel=0, control=64, value=127), 0),
            _event(0.2, Message("note_on", channel=0, note=60, velocity=91), 0),
            _event(0.4, Message("note_off", channel=0, note=60, velocity=0), 0),
            _event(0.5, Message("control_change", channel=0, control=64, value=0), 0),
            _event(0.0, Message("program_change", channel=1, program=40), 1),
            _event(0.2, Message("note_on", channel=1, note=67, velocity=73), 1),
            _event(0.4, Message("note_off", channel=1, note=67, velocity=0), 1),
            _event(0.1, Message("note_on", channel=9, note=36, velocity=110), 2),
            _event(0.2, Message("note_off", channel=9, note=36, velocity=0), 2),
        ),
        duration_seconds=0.5,
    )


def test_original_rendering_is_the_exact_existing_timeline() -> None:
    timeline = _sample_timeline()

    assert render_timeline(timeline) is timeline
    assert render_timeline(timeline, RenderingPolicy(RenderingMode.ORIGINAL)) is timeline


def test_piano_only_suppresses_drums_and_source_program_bank_state() -> None:
    rendered = render_timeline(
        _sample_timeline(),
        RenderingPolicy(mode=RenderingMode.PIANO_ONLY),
    )

    assert rendered.duration_seconds == 0.5
    assert all(getattr(event.message, "channel", None) != 9 for event in rendered.events)
    assert not any(
        event.message.type == "control_change" and event.message.control in {0, 32}
        for event in rendered.events
    )

    program_events = [event for event in rendered.events if event.message.type == "program_change"]
    assert [(event.track_index, event.message.channel, event.message.program) for event in program_events] == [
        (0, 0, 0),
        (1, 1, 0),
    ]


def test_piano_only_preserves_velocity_sustain_timing_and_track_identity() -> None:
    rendered = render_timeline(
        _sample_timeline(),
        RenderingPolicy(mode=RenderingMode.PIANO_ONLY),
    )

    note = next(
        event
        for event in rendered.events
        if event.message.type == "note_on" and event.message.channel == 0
    )
    assert note.at_seconds == 0.2
    assert note.track_index == 0
    assert note.message.velocity == 91

    sustain = [
        event
        for event in rendered.events
        if event.message.type == "control_change" and event.message.control == 64
    ]
    assert [(event.at_seconds, event.message.value) for event in sustain] == [(0.1, 127), (0.5, 0)]

    first_note_index = rendered.events.index(note)
    injected = rendered.events[first_note_index - 1]
    assert injected.at_seconds == note.at_seconds
    assert injected.track_index == note.track_index
    assert injected.message.type == "program_change"
    assert injected.message.program == 0


def test_channel_override_wins_without_touching_other_channels() -> None:
    rendered = render_timeline(
        _sample_timeline(),
        RenderingPolicy(
            mode=RenderingMode.OVERRIDE,
            program_overrides=(ProgramOverride(channel=0, program=24),),
        ),
    )

    channel_zero_programs = [
        event.message.program
        for event in rendered.events
        if event.message.type == "program_change" and event.message.channel == 0
    ]
    channel_one_programs = [
        event.message.program
        for event in rendered.events
        if event.message.type == "program_change" and event.message.channel == 1
    ]
    assert channel_zero_programs == [24]
    assert channel_one_programs == [40]
    assert any(getattr(event.message, "channel", None) == 9 for event in rendered.events)


def test_explicit_override_wins_over_piano_only_default() -> None:
    rendered = render_timeline(
        _sample_timeline(),
        RenderingPolicy(
            mode=RenderingMode.PIANO_ONLY,
            program_overrides=(ProgramOverride(channel=1, program=6),),
        ),
    )

    programs = {
        (event.track_index, event.message.channel): event.message.program
        for event in rendered.events
        if event.message.type == "program_change"
    }
    assert programs[(0, 0)] == 0
    assert programs[(1, 1)] == 6


def test_rendered_program_state_is_available_to_resume_priming() -> None:
    rendered = render_timeline(
        _sample_timeline(),
        RenderingPolicy(mode=RenderingMode.PIANO_ONLY),
    )

    priming = rendered.priming_events(0.3)
    programs = [event for event in priming if event.message.type == "program_change"]
    assert {(event.track_index, event.message.channel, event.message.program) for event in programs} == {
        (0, 0, 0),
        (1, 1, 0),
    }


def test_program_is_injected_for_each_track_specific_part_on_shared_channel() -> None:
    timeline = MidiTimeline(
        events=(
            _event(0.1, Message("note_on", channel=0, note=60, velocity=80), 1),
            _event(0.1, Message("note_on", channel=0, note=72, velocity=80), 2),
        ),
        duration_seconds=0.1,
    )
    rendered = render_timeline(timeline, RenderingPolicy(mode=RenderingMode.PIANO_ONLY))

    programs = [event for event in rendered.events if event.message.type == "program_change"]
    assert [(event.track_index, event.message.channel, event.message.program) for event in programs] == [
        (1, 0, 0),
        (2, 0, 0),
    ]


@pytest.mark.parametrize(
    "override, message",
    [
        (lambda: ProgramOverride(channel=-1, program=0), "channel"),
        (lambda: ProgramOverride(channel=16, program=0), "channel"),
        (lambda: ProgramOverride(channel=9, program=0), "percussion"),
        (lambda: ProgramOverride(channel=0, program=-1), "program"),
        (lambda: ProgramOverride(channel=0, program=128), "program"),
    ],
)
def test_invalid_program_override_is_rejected(override, message: str) -> None:
    with pytest.raises(RenderingError, match=message):
        override()


def test_duplicate_channel_overrides_are_rejected() -> None:
    with pytest.raises(RenderingError, match="one program override"):
        RenderingPolicy(
            mode=RenderingMode.OVERRIDE,
            program_overrides=(
                ProgramOverride(channel=0, program=0),
                ProgramOverride(channel=0, program=40),
            ),
        )


def test_override_mode_requires_an_override() -> None:
    with pytest.raises(RenderingError, match="requires at least one"):
        RenderingPolicy(mode=RenderingMode.OVERRIDE)
