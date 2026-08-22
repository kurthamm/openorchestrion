from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from mido import Message, MidiFile


@dataclass(frozen=True, slots=True)
class MidiTimelineEvent:
    at_seconds: float
    message: Message


@dataclass(frozen=True, slots=True)
class MidiTimeline:
    events: tuple[MidiTimelineEvent, ...]
    duration_seconds: float

    @classmethod
    def from_file(cls, path: str | Path) -> "MidiTimeline":
        source = Path(path)
        if not source.is_file():
            raise FileNotFoundError(source)
        midi = MidiFile(source)
        current = 0.0
        events: list[MidiTimelineEvent] = []
        for message in midi:
            current += float(message.time)
            if message.is_meta:
                continue
            events.append(MidiTimelineEvent(current, message.copy(time=0)))
        return cls(tuple(events), current)

    def priming_messages(self, position_seconds: float) -> tuple[Message, ...]:
        """Return the most recent stateful channel messages before a resume point."""
        if position_seconds <= 0:
            return ()
        latest: dict[tuple[object, ...], MidiTimelineEvent] = {}
        for event in self.events:
            if event.at_seconds >= position_seconds:
                break
            message = event.message
            key: tuple[object, ...] | None = None
            if message.type == "control_change":
                key = ("control_change", message.channel, message.control)
            elif message.type == "program_change":
                key = ("program_change", message.channel)
            elif message.type == "pitchwheel":
                key = ("pitchwheel", message.channel)
            elif message.type == "aftertouch":
                key = ("aftertouch", message.channel)
            if key is not None:
                latest[key] = event
        ordered = sorted(latest.values(), key=lambda event: event.at_seconds)
        return tuple(event.message.copy(time=0) for event in ordered)
