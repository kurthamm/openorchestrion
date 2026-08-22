from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from openorchestrion.midi.router import RoutingPlan


@dataclass(frozen=True, slots=True)
class QueueItemSpec:
    asset_id: str
    title: str
    duration_seconds: float
    midi_path: str
    composition_id: str | None = None
    composer: str | None = None
    routing_plan: RoutingPlan | None = None


@dataclass(slots=True)
class RuntimeQueueItem:
    spec: QueueItemSpec
    play_id: str | None = None


@dataclass(frozen=True, slots=True)
class QueueEntrySnapshot:
    asset_id: str
    composition_id: str | None
    title: str
    composer: str | None
    duration_seconds: float
    index: int


@dataclass(frozen=True, slots=True)
class QueueSnapshot:
    items: tuple[QueueEntrySnapshot, ...]
    current_index: int | None
    total_duration_seconds: float
    command_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["items"] = [asdict(item) for item in self.items]
        return value


@dataclass(frozen=True, slots=True)
class PositionSnapshot:
    position_ms: int
    duration_ms: int | None
    rate: float
    server_time: str


@dataclass(frozen=True, slots=True)
class NowPlayingSnapshot:
    asset_id: str
    composition_id: str | None
    title: str
    composer: str | None
    duration_seconds: float
    queue_index: int | None


@dataclass(frozen=True, slots=True)
class PlaybackSnapshot:
    state: str
    now_playing: NowPlayingSnapshot | None
    position: PositionSnapshot | None
    command_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
