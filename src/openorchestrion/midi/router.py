from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(slots=True)
class MidiRoute:
    """Route one MIDI source part to an output device.

    `source_channel` and `destination_channel` use Mido's zero-based 0..15
    convention. `source_track` is the zero-based Standard MIDI File track index.

    A route may match a channel across every track, or a specific track/channel
    pair. Multiple matching routes intentionally broadcast the same source part
    to multiple outputs.
    """

    source_channel: int | None
    destination_device: str
    destination_channel: int | None = None
    latency_offset_ms: float = 0.0
    source_track: int | None = None

    def matches(self, channel: int | None, track_index: int | None) -> bool:
        if self.source_channel is not None and self.source_channel != channel:
            return False
        if self.source_track is not None and self.source_track != track_index:
            return False
        return True

    @property
    def specificity(self) -> int:
        return int(self.source_channel is not None) + int(self.source_track is not None)


@dataclass(slots=True)
class RoutingPlan:
    """Deterministic mapping from MIDI channels/tracks to output devices.

    The current safe failure policy is `stop`: if an explicitly routed output is
    unavailable, playback raises and the engine performs its normal panic fan-out.
    `drop` is available for intentionally disposable accompaniment parts, but is
    never selected by the automatic planner today.
    """

    routes: list[MidiRoute] = field(default_factory=list)
    failure_policy: Literal["stop", "drop"] = "stop"
    diagnostics: list[str] = field(default_factory=list)

    def destinations_for(
        self,
        channel: int | None,
        track_index: int | None = None,
    ) -> tuple[MidiRoute, ...]:
        matches = [route for route in self.routes if route.matches(channel, track_index)]
        if not matches:
            return ()
        # A track+channel route overrides a broader channel-only/track-only route.
        most_specific = max(route.specificity for route in matches)
        return tuple(route for route in matches if route.specificity == most_specific)

    def destination_for(self, channel: int) -> MidiRoute | None:
        """Backward-compatible single-route lookup used by older callers."""
        matches = self.destinations_for(channel)
        return matches[0] if matches else None
