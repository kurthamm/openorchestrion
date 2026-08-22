from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class MidiRoute:
    """Route one Mido channel to an output device.

    `source_channel` and `destination_channel` use Mido's zero-based 0..15
    convention. User-facing documentation may call those MIDI channels 1..16.
    """

    source_channel: int
    destination_device: str
    destination_channel: int | None = None
    latency_offset_ms: float = 0.0


@dataclass(slots=True)
class RoutingPlan:
    """Deterministic mapping from zero-based MIDI channels to output devices."""

    routes: list[MidiRoute] = field(default_factory=list)

    def destination_for(self, channel: int) -> MidiRoute | None:
        for route in self.routes:
            if route.source_channel == channel:
                return route
        return None
