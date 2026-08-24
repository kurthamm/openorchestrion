"""Non-destructive playback-time MIDI rendering policies.

Rendering never rewrites an imported MIDI object or its sidecar.  It transforms
an already parsed :class:`MidiTimeline` for one playback attempt, preserving the
master clock plus source track/channel identity used by routing.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from mido import Message

from openorchestrion.midi import GMProgramError, resolve_gm_program

from .timeline import MidiTimeline, MidiTimelineEvent


class RenderingError(ValueError):
    """A rendering policy that cannot be applied deterministically."""


class RenderingMode(StrEnum):
    ORIGINAL = "ORIGINAL"
    PIANO_ONLY = "PIANO_ONLY"
    OVERRIDE = "OVERRIDE"


@dataclass(frozen=True, slots=True)
class ProgramOverride:
    """Force one MIDI channel to a General MIDI program for this playback.

    MIDI Program Change is channel state, so channel is the first stable selector
    supported by the renderer.  Track-specific overrides require destination-aware
    validation when two tracks share a channel and are intentionally deferred to
    the routing-integrated slice of Issue #56 rather than pretending track state
    exists in MIDI when it does not.
    """

    channel: int
    program: int

    def __post_init__(self) -> None:
        if not 0 <= self.channel <= 15:
            raise RenderingError("override channel must be between 0 and 15")
        if self.channel == 9:
            raise RenderingError("channel 10 is percussion and cannot receive a pitched program override")
        if not 0 <= self.program <= 127:
            raise RenderingError("override program must be between 0 and 127")

    @classmethod
    def from_value(cls, channel: int, program: int | str) -> "ProgramOverride":
        """Resolve a MIDI-native integer or canonical GM patch name at the domain boundary."""
        try:
            resolved = resolve_gm_program(program)
        except GMProgramError as exc:
            raise RenderingError(str(exc)) from None
        return cls(channel=channel, program=resolved)


@dataclass(frozen=True, slots=True)
class RenderingPolicy:
    mode: RenderingMode = RenderingMode.ORIGINAL
    program_overrides: tuple[ProgramOverride, ...] = ()
    piano_program: int = 0

    def __post_init__(self) -> None:
        if not 0 <= self.piano_program <= 7:
            raise RenderingError("piano_program must be a General MIDI piano program (0..7)")
        channels = [override.channel for override in self.program_overrides]
        if len(channels) != len(set(channels)):
            raise RenderingError("only one program override may target a MIDI channel")
        if self.mode is RenderingMode.OVERRIDE and not self.program_overrides:
            raise RenderingError("OVERRIDE rendering requires at least one program override")

    @classmethod
    def from_values(
        cls,
        *,
        mode: RenderingMode | str = RenderingMode.ORIGINAL,
        program_overrides: Iterable[tuple[int, int | str]] = (),
        piano_program: int | str = 0,
    ) -> "RenderingPolicy":
        """Build a validated policy from request-friendly primitive selectors.

        This is the application seam the eventual HTTP model should call.  GM
        names are resolved here, not in a route handler, so CLI/automation/UI
        callers all share one numbering and ambiguity policy.
        """
        try:
            rendering_mode = mode if isinstance(mode, RenderingMode) else RenderingMode(mode)
        except ValueError:
            allowed = ", ".join(member.value for member in RenderingMode)
            raise RenderingError(f"rendering mode must be one of {allowed}") from None

        try:
            resolved_piano = resolve_gm_program(piano_program)
        except GMProgramError as exc:
            raise RenderingError(str(exc)) from None

        overrides = tuple(
            ProgramOverride.from_value(channel, program)
            for channel, program in program_overrides
        )
        return cls(
            mode=rendering_mode,
            program_overrides=overrides,
            piano_program=resolved_piano,
        )

    @property
    def is_identity(self) -> bool:
        return self.mode is RenderingMode.ORIGINAL and not self.program_overrides


def _channel(message: Message) -> int | None:
    value = getattr(message, "channel", None)
    return int(value) if value is not None else None


def _is_bank_select(message: Message) -> bool:
    return message.type == "control_change" and int(message.control) in {0, 32}


def _is_note_start(message: Message) -> bool:
    return message.type == "note_on" and int(message.velocity) > 0


def render_timeline(
    timeline: MidiTimeline,
    policy: RenderingPolicy | None = None,
) -> MidiTimeline:
    """Return the timeline heard under ``policy`` without mutating the source.

    Precedence is source arrangement < rendering mode < explicit channel
    override.  A forced program is injected immediately before that channel's
    first sounding note on each source track.  Repeating the injection per
    track/channel is intentional: track-specific routes may send parts sharing a
    MIDI channel to different physical outputs, and each destination must receive
    the chosen program before its notes.
    """

    policy = policy or RenderingPolicy()
    if policy.is_identity:
        # Strong compatibility guarantee: no policy means not even a copied
        # timeline.  Existing playback sees exactly the object it saw before.
        return timeline

    overrides = {entry.channel: entry.program for entry in policy.program_overrides}
    primed_parts: set[tuple[int | None, int]] = set()
    rendered: list[MidiTimelineEvent] = []

    for event in timeline.events:
        message = event.message
        channel = _channel(message)

        if policy.mode is RenderingMode.PIANO_ONLY and channel == 9:
            # General MIDI channel 10 is percussion.  Turning drum note numbers
            # into piano pitches is not a piano reduction, so the channel is
            # suppressed instead.
            continue

        forced_program: int | None = None
        if channel is not None:
            if channel in overrides:
                forced_program = overrides[channel]
            elif policy.mode is RenderingMode.PIANO_ONLY:
                forced_program = policy.piano_program

        if forced_program is not None and (
            message.type == "program_change" or _is_bank_select(message)
        ):
            # Source bank/program state must not undo the rendering decision.
            continue

        if forced_program is not None and _is_note_start(message):
            part = (event.track_index, channel)
            if part not in primed_parts:
                rendered.append(
                    MidiTimelineEvent(
                        at_seconds=event.at_seconds,
                        message=Message(
                            "program_change",
                            channel=channel,
                            program=forced_program,
                            time=0,
                        ),
                        track_index=event.track_index,
                    )
                )
                primed_parts.add(part)

        rendered.append(event)

    return MidiTimeline(tuple(rendered), timeline.duration_seconds)


__all__ = [
    "ProgramOverride",
    "RenderingError",
    "RenderingMode",
    "RenderingPolicy",
    "render_timeline",
]
