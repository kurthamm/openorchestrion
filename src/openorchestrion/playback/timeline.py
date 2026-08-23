from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import mido
from mido import Message, MidiFile


@dataclass(frozen=True, slots=True)
class MidiTimelineEvent:
    at_seconds: float
    message: Message
    track_index: int | None = None


@dataclass(frozen=True, slots=True)
class MidiTimeline:
    events: tuple[MidiTimelineEvent, ...]
    duration_seconds: float

    @classmethod
    def from_file(cls, path: str | Path) -> "MidiTimeline":
        """Build one tempo-aware timeline while preserving source track identity."""
        source = Path(path)
        if not source.is_file():
            raise FileNotFoundError(source)
        midi = MidiFile(source)

        absolute: list[tuple[int, int, int, object]] = []
        for track_index, track in enumerate(midi.tracks):
            tick = 0
            for sequence_index, message in enumerate(track):
                tick += int(message.time)
                absolute.append((tick, track_index, sequence_index, message))
        absolute.sort(key=lambda value: (value[0], value[1], value[2]))

        tempo = 500_000  # Standard MIDI default: 120 BPM.
        current_tick = 0
        current_seconds = 0.0
        events: list[MidiTimelineEvent] = []
        for tick, track_index, _, message in absolute:
            delta_ticks = tick - current_tick
            if delta_ticks:
                current_seconds += mido.tick2second(delta_ticks, midi.ticks_per_beat, tempo)
                current_tick = tick
            if message.is_meta:
                if message.type == "set_tempo":
                    tempo = int(message.tempo)
                continue
            events.append(
                MidiTimelineEvent(
                    current_seconds,
                    message.copy(time=0),
                    track_index=track_index,
                )
            )
        return cls(tuple(events), current_seconds)

    def priming_events(self, position_seconds: float) -> tuple[MidiTimelineEvent, ...]:
        """Return stateful events needed to resume at a position.

        Track identity is retained so a track-specific route is primed on the
        same destination that receives the subsequent musical events.
        """
        if position_seconds <= 0:
            return ()
        latest: dict[tuple[object, ...], MidiTimelineEvent] = {}
        for event in self.events:
            if event.at_seconds >= position_seconds:
                break
            message = event.message
            key: tuple[object, ...] | None = None
            if message.type == "control_change":
                key = (
                    "control_change",
                    event.track_index,
                    message.channel,
                    message.control,
                )
            elif message.type == "program_change":
                key = ("program_change", event.track_index, message.channel)
            elif message.type == "pitchwheel":
                key = ("pitchwheel", event.track_index, message.channel)
            elif message.type == "aftertouch":
                key = ("aftertouch", event.track_index, message.channel)
            if key is not None:
                latest[key] = event
        return tuple(sorted(latest.values(), key=lambda event: event.at_seconds))

    def priming_messages(self, position_seconds: float) -> tuple[Message, ...]:
        """Backward-compatible message-only view of :meth:`priming_events`."""
        return tuple(
            event.message.copy(time=0) for event in self.priming_events(position_seconds)
        )
