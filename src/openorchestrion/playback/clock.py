from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    def now(self) -> float: ...

    def utcnow(self) -> datetime: ...

    async def sleep_until(self, deadline: float) -> None: ...


class SystemClock:
    def now(self) -> float:
        return time.monotonic()

    def utcnow(self) -> datetime:
        return datetime.now(UTC)

    async def sleep_until(self, deadline: float) -> None:
        delay = deadline - self.now()
        if delay > 0:
            await asyncio.sleep(delay)


@dataclass(slots=True)
class _Waiter:
    deadline: float
    future: asyncio.Future[None]


class ManualClock:
    """Deterministic monotonic and wall clock for scheduler tests."""

    def __init__(self, *, start: float = 0.0, wall_start: datetime | None = None) -> None:
        self._now = float(start)
        self._wall_start = wall_start or datetime(2026, 1, 1, tzinfo=UTC)
        if self._wall_start.tzinfo is None:
            raise ValueError("wall_start must be timezone-aware")
        self._monotonic_start = float(start)
        self._waiters: list[_Waiter] = []

    def now(self) -> float:
        return self._now

    def utcnow(self) -> datetime:
        return self._wall_start + timedelta(seconds=self._now - self._monotonic_start)

    async def sleep_until(self, deadline: float) -> None:
        if deadline <= self._now:
            await asyncio.sleep(0)
            return
        loop = asyncio.get_running_loop()
        future: asyncio.Future[None] = loop.create_future()
        waiter = _Waiter(float(deadline), future)
        self._waiters.append(waiter)
        self._waiters.sort(key=lambda value: value.deadline)
        try:
            await future
        finally:
            if waiter in self._waiters:
                self._waiters.remove(waiter)

    async def advance(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("seconds must be non-negative")
        await asyncio.sleep(0)
        self._now += float(seconds)
        for _ in range(1000):
            due = [waiter for waiter in self._waiters if waiter.deadline <= self._now]
            if not due:
                # Let awakened scheduler tasks run and potentially schedule more
                # immediately-due waits before declaring the clock quiescent.
                for _yield in range(20):
                    await asyncio.sleep(0)
                    due = [waiter for waiter in self._waiters if waiter.deadline <= self._now]
                    if due:
                        break
                if not due:
                    return
            for waiter in due:
                if not waiter.future.done():
                    waiter.future.set_result(None)
            await asyncio.sleep(0)
        raise RuntimeError("manual clock did not quiesce")
