from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from .clock import Clock


@dataclass(frozen=True, slots=True)
class PlaybackEvent:
    type: str
    seq: int
    ts: str
    payload: dict[str, Any]


class PlaybackEventBus:
    """Small in-process fan-out bus for authoritative playback state deltas."""

    def __init__(self, clock: Clock, *, subscriber_queue_size: int = 128) -> None:
        self.clock = clock
        self.subscriber_queue_size = subscriber_queue_size
        self._seq = 0
        self._subscribers: set[asyncio.Queue[PlaybackEvent]] = set()

    @property
    def seq(self) -> int:
        return self._seq

    def subscribe(self) -> asyncio.Queue[PlaybackEvent]:
        queue: asyncio.Queue[PlaybackEvent] = asyncio.Queue(maxsize=self.subscriber_queue_size)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[PlaybackEvent]) -> None:
        self._subscribers.discard(queue)

    def publish(self, event_type: str, payload: dict[str, Any]) -> PlaybackEvent:
        self._seq += 1
        event = PlaybackEvent(
            type=event_type,
            seq=self._seq,
            ts=self.clock.utcnow().isoformat(),
            payload=payload,
        )
        for queue in tuple(self._subscribers):
            if queue.full():
                # Dropping the oldest event deliberately creates a sequence gap.
                # The API contract tells that client to request a fresh snapshot.
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass
        return event
