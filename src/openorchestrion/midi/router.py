from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class MidiRoute:
    source_channel: int
    destination_device: str
    destination_channel: int | None = None
    latency_offset_ms: float = 0.0


@dataclass(slots=True)
class RoutingPlan:
    """Deterministic mapping from MIDI channels/parts to output devices."""

    routes: list[MidiRoute] = field(default_factory=list)

    def destination_for(self, channel: int) -> MidiRoute | None:
        for route in self.routes:
            if route.source_channel == channel:
                return route
        return None
