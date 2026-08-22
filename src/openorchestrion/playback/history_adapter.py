from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Protocol

from .clock import Clock


class HistoryRecorder(Protocol):
    async def queued(
        self,
        *,
        asset_id: str,
        composition_id: str | None,
        duration_seconds: float,
    ) -> str: ...

    async def started(self, play_id: str) -> None: ...

    async def progress(self, play_id: str, played_seconds: float) -> None: ...

    async def completed(self, play_id: str, played_seconds: float) -> None: ...

    async def skipped(self, play_id: str, played_seconds: float) -> None: ...

    async def failed(self, play_id: str, played_seconds: float, error: str) -> None: ...


class SqliteHistoryRecorder:
    """Async adapter around the durable SQLite history module."""

    def __init__(self, db_path: str | Path, clock: Clock) -> None:
        self.db_path = Path(db_path)
        self.clock = clock

    async def queued(
        self,
        *,
        asset_id: str,
        composition_id: str | None,
        duration_seconds: float,
    ) -> str:
        from openorchestrion.history import queue_play

        return await asyncio.to_thread(
            queue_play,
            self.db_path,
            asset_id=asset_id,
            composition_id=composition_id,
            track_duration_seconds=duration_seconds,
            occurred_at=self.clock.utcnow(),
        )

    async def started(self, play_id: str) -> None:
        from openorchestrion.history import mark_started

        await asyncio.to_thread(
            mark_started,
            self.db_path,
            play_id,
            occurred_at=self.clock.utcnow(),
        )

    async def progress(self, play_id: str, played_seconds: float) -> None:
        from openorchestrion.history import update_progress

        await asyncio.to_thread(
            update_progress,
            self.db_path,
            play_id,
            played_seconds,
            occurred_at=self.clock.utcnow(),
        )

    async def completed(self, play_id: str, played_seconds: float) -> None:
        from openorchestrion.history import mark_completed

        await asyncio.to_thread(
            mark_completed,
            self.db_path,
            play_id,
            occurred_at=self.clock.utcnow(),
            played_seconds=played_seconds,
        )

    async def skipped(self, play_id: str, played_seconds: float) -> None:
        from openorchestrion.history import mark_skipped

        await asyncio.to_thread(
            mark_skipped,
            self.db_path,
            play_id,
            occurred_at=self.clock.utcnow(),
            played_seconds=played_seconds,
        )

    async def failed(self, play_id: str, played_seconds: float, error: str) -> None:
        from openorchestrion.history import mark_failed

        await asyncio.to_thread(
            mark_failed,
            self.db_path,
            play_id,
            occurred_at=self.clock.utcnow(),
            played_seconds=played_seconds,
            error=error,
        )
