from __future__ import annotations

import asyncio
from collections import OrderedDict
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Sequence

from openorchestrion.midi.router import RoutingPlan

from .clock import Clock, SystemClock
from .events import PlaybackEventBus
from .history_adapter import HistoryRecorder
from .models import (
    NowPlayingSnapshot,
    PlaybackSnapshot,
    PositionSnapshot,
    QueueEntrySnapshot,
    QueueItemSpec,
    QueueSnapshot,
    RuntimeQueueItem,
)
from .outputs import MidiOutputRouter, PlaybackOutputError, RoutedMessage
from .timeline import MidiTimeline

PlaybackStateName = Literal["idle", "playing", "paused", "stopped"]


class PlaybackError(RuntimeError):
    pass


class PlaybackConflict(PlaybackError):
    pass


@dataclass(frozen=True, slots=True)
class _Dispatch:
    musical_at: float
    send_at: float
    routed: RoutedMessage


class PlaybackEngine:
    """Server-owned queue, transport, scheduler, history and MIDI output state."""

    def __init__(
        self,
        *,
        router: MidiOutputRouter,
        history: HistoryRecorder,
        clock: Clock | None = None,
        event_bus: PlaybackEventBus | None = None,
        command_cache_size: int = 256,
    ) -> None:
        self.clock = clock or SystemClock()
        self.router = router
        self.history = history
        self.events = event_bus or PlaybackEventBus(self.clock)
        self.command_cache_size = command_cache_size
        self._lock = asyncio.Lock()
        self._send_lock = asyncio.Lock()
        self._queue: list[RuntimeQueueItem] = []
        self._current_index: int | None = None
        self._state: PlaybackStateName = "idle"
        self._position_seconds = 0.0
        self._active_duration_seconds: float | None = None
        self._run_anchor_clock: float | None = None
        self._worker: asyncio.Task[None] | None = None
        self._generation = 0
        self._commands: OrderedDict[str, str] = OrderedDict()
        self._closed = False

    @property
    def output_names(self) -> tuple[str, ...]:
        return self.router.output_names

    @property
    def outputs_ready(self) -> bool:
        return self.router.ready

    def _check_command(self, command_id: str | None, operation: str) -> bool:
        """Return False for a successful prior command; do not cache failures."""
        if command_id is None:
            return True
        previous = self._commands.get(command_id)
        if previous is None:
            return True
        if previous != operation:
            raise PlaybackConflict(
                f"command_id {command_id} was already used for {previous}, not {operation}"
            )
        self._commands.move_to_end(command_id)
        return False

    def _remember_command(self, command_id: str | None, operation: str) -> None:
        if command_id is None:
            return
        self._commands[command_id] = operation
        self._commands.move_to_end(command_id)
        while len(self._commands) > self.command_cache_size:
            self._commands.popitem(last=False)

    def _current_item_locked(self) -> RuntimeQueueItem | None:
        if self._current_index is None:
            return None
        if not 0 <= self._current_index < len(self._queue):
            return None
        return self._queue[self._current_index]

    def _position_now_locked(self) -> float:
        position = self._position_seconds
        if self._state == "playing" and self._run_anchor_clock is not None:
            position += max(0.0, self.clock.now() - self._run_anchor_clock)
        duration = self._active_duration_seconds
        if duration is None:
            current = self._current_item_locked()
            duration = current.spec.duration_seconds if current else None
        if duration is not None:
            position = min(position, duration)
        return max(0.0, position)

    def _queue_snapshot_locked(self, command_id: str | None = None) -> QueueSnapshot:
        items = tuple(
            QueueEntrySnapshot(
                asset_id=item.spec.asset_id,
                composition_id=item.spec.composition_id,
                title=item.spec.title,
                composer=item.spec.composer,
                duration_seconds=item.spec.duration_seconds,
                index=index,
            )
            for index, item in enumerate(self._queue)
        )
        return QueueSnapshot(
            items=items,
            current_index=self._current_index,
            total_duration_seconds=sum(item.spec.duration_seconds for item in self._queue),
            command_id=command_id,
        )

    def _playback_snapshot_locked(self, command_id: str | None = None) -> PlaybackSnapshot:
        current = self._current_item_locked()
        now_playing = None
        position = None
        if current is not None:
            now_playing = NowPlayingSnapshot(
                asset_id=current.spec.asset_id,
                composition_id=current.spec.composition_id,
                title=current.spec.title,
                composer=current.spec.composer,
                duration_seconds=current.spec.duration_seconds,
                queue_index=self._current_index,
            )
            rate = 1.0 if self._state == "playing" else 0.0
            duration = self._active_duration_seconds or current.spec.duration_seconds
            position = PositionSnapshot(
                position_ms=round(self._position_now_locked() * 1000),
                duration_ms=round(duration * 1000),
                rate=rate,
                server_time=self.clock.utcnow().isoformat(),
            )
        return PlaybackSnapshot(
            state=self._state,
            now_playing=now_playing,
            position=position,
            command_id=command_id,
        )

    async def queue_snapshot(self, *, command_id: str | None = None) -> QueueSnapshot:
        async with self._lock:
            return self._queue_snapshot_locked(command_id)

    async def playback_snapshot(self, *, command_id: str | None = None) -> PlaybackSnapshot:
        async with self._lock:
            return self._playback_snapshot_locked(command_id)

    async def snapshots(self) -> tuple[PlaybackSnapshot, QueueSnapshot]:
        async with self._lock:
            return self._playback_snapshot_locked(), self._queue_snapshot_locked()

    async def set_queue(
        self,
        items: Sequence[QueueItemSpec],
        *,
        mode: Literal["replace", "append"] = "replace",
        command_id: str | None = None,
    ) -> QueueSnapshot:
        if not items:
            raise PlaybackConflict("queue request produced no items")
        incoming_ids = [item.asset_id for item in items]
        if len(set(incoming_ids)) != len(incoming_ids):
            raise PlaybackConflict("queue cannot contain duplicate asset_id values")
        async with self._lock:
            operation = f"queue:{mode}"
            if not self._check_command(command_id, operation):
                return self._queue_snapshot_locked(command_id)
            if mode == "append":
                existing = {item.spec.asset_id for item in self._queue}
                duplicates = existing.intersection(incoming_ids)
                if duplicates:
                    raise PlaybackConflict(
                        f"queue already contains asset(s): {', '.join(sorted(duplicates))}"
                    )
            if mode == "replace":
                await self._interrupt_locked(mark_skipped=True, reset_position=True)
            runtime: list[RuntimeQueueItem] = []
            for spec in items:
                play_id = await self.history.queued(
                    asset_id=spec.asset_id,
                    composition_id=spec.composition_id,
                    duration_seconds=spec.duration_seconds,
                )
                runtime.append(RuntimeQueueItem(spec=spec, play_id=play_id))
            if mode == "replace":
                self._queue = runtime
                self._current_index = 0
                self._state = "idle"
                self._position_seconds = 0.0
                self._active_duration_seconds = None
                self._run_anchor_clock = None
                self.events.publish("state.playback", self._playback_snapshot_locked().to_dict())
            else:
                was_empty = not self._queue
                self._queue.extend(runtime)
                if was_empty:
                    self._current_index = 0
                    self._state = "idle"
            snapshot = self._queue_snapshot_locked(command_id)
            self._remember_command(command_id, operation)
            self.events.publish("state.queue", snapshot.to_dict())
            return snapshot

    async def reorder(
        self,
        asset_id: str,
        to_index: int,
        *,
        command_id: str | None = None,
    ) -> QueueSnapshot:
        async with self._lock:
            operation = "queue:reorder"
            if not self._check_command(command_id, operation):
                return self._queue_snapshot_locked(command_id)
            if not 0 <= to_index < len(self._queue):
                raise PlaybackConflict("to_index is outside the queue")
            source_index = next(
                (i for i, item in enumerate(self._queue) if item.spec.asset_id == asset_id), None
            )
            if source_index is None:
                raise PlaybackConflict(f"asset is not in the queue: {asset_id}")
            current = self._current_item_locked()
            item = self._queue.pop(source_index)
            self._queue.insert(to_index, item)
            if current is not None:
                self._current_index = self._queue.index(current)
            snapshot = self._queue_snapshot_locked(command_id)
            self._remember_command(command_id, operation)
            self.events.publish("state.queue", snapshot.to_dict())
            return snapshot

    async def remove(
        self,
        asset_id: str,
        *,
        command_id: str | None = None,
    ) -> QueueSnapshot:
        async with self._lock:
            operation = "queue:remove"
            if not self._check_command(command_id, operation):
                return self._queue_snapshot_locked(command_id)
            index = next(
                (i for i, item in enumerate(self._queue) if item.spec.asset_id == asset_id), None
            )
            if index is None:
                raise PlaybackConflict(f"asset is not in the queue: {asset_id}")
            active = index == self._current_index
            was_active = self._state in {"playing", "paused"}
            if active and was_active:
                await self._interrupt_locked(mark_skipped=True, reset_position=True)
            self._queue.pop(index)
            if not self._queue:
                self._current_index = None
                self._state = "idle"
                self._position_seconds = 0.0
                self._active_duration_seconds = None
            elif active:
                self._current_index = min(index, len(self._queue) - 1)
            elif self._current_index is not None and index < self._current_index:
                self._current_index -= 1
            snapshot = self._queue_snapshot_locked(command_id)
            self.events.publish("state.queue", snapshot.to_dict())
            self.events.publish("state.playback", self._playback_snapshot_locked().to_dict())
            if active and was_active and self._current_index is not None:
                await self._begin_current_locked(start_position=0.0)
            self._remember_command(command_id, operation)
            return snapshot

    async def transport(
        self,
        action: Literal["play", "pause", "stop", "skip", "panic"],
        *,
        command_id: str | None = None,
    ) -> PlaybackSnapshot:
        async with self._lock:
            operation = f"transport:{action}"
            if not self._check_command(command_id, operation):
                return self._playback_snapshot_locked(command_id)
            if action == "play":
                await self._play_locked()
            elif action == "pause":
                await self._pause_locked()
            elif action == "stop":
                was_active = self._state in {"playing", "paused"}
                await self._interrupt_locked(mark_skipped=True, reset_position=True)
                if not was_active:
                    await self._panic_locked()
                if self._queue:
                    self._state = "stopped"
            elif action == "skip":
                await self._skip_locked()
            elif action == "panic":
                was_active = self._state in {"playing", "paused"}
                await self._interrupt_locked(mark_skipped=True, reset_position=True)
                if not was_active:
                    await self._panic_locked()
                if self._queue:
                    self._state = "stopped"
            snapshot = self._playback_snapshot_locked(command_id)
            self._remember_command(command_id, operation)
            self.events.publish("state.playback", snapshot.to_dict())
            return snapshot

    async def _play_locked(self) -> None:
        if not self._queue or self._current_index is None:
            raise PlaybackConflict("the queue is empty")
        if self._state == "playing":
            return
        start_position = self._position_seconds if self._state == "paused" else 0.0
        await self._begin_current_locked(start_position=start_position)

    async def _pause_locked(self) -> None:
        if self._state != "playing":
            raise PlaybackConflict("pause requires active playback")
        position = self._position_now_locked()
        self._generation += 1
        if self._worker is not None and not self._worker.done():
            self._worker.cancel()
        self._worker = None
        self._position_seconds = position
        self._run_anchor_clock = None
        self._state = "paused"
        current = self._current_item_locked()
        if current is not None and current.play_id is not None:
            await self.history.progress(current.play_id, position)
        await self._panic_locked()

    async def _skip_locked(self) -> None:
        if self._current_index is None or not self._queue:
            raise PlaybackConflict("the queue is empty")
        was_active = self._state in {"playing", "paused"}
        if was_active:
            await self._interrupt_locked(mark_skipped=True, reset_position=True)
        if self._current_index + 1 >= len(self._queue):
            self._state = "stopped"
            self._position_seconds = 0.0
            return
        self._current_index += 1
        self._position_seconds = 0.0
        self._active_duration_seconds = None
        self.events.publish("state.queue", self._queue_snapshot_locked().to_dict())
        if was_active:
            await self._begin_current_locked(start_position=0.0)
        else:
            self._state = "stopped"

    async def _interrupt_locked(self, *, mark_skipped: bool, reset_position: bool) -> None:
        position = self._position_now_locked()
        active = self._state in {"playing", "paused"}
        self._generation += 1
        if self._worker is not None and not self._worker.done():
            self._worker.cancel()
        self._worker = None
        current = self._current_item_locked()
        if active and current is not None and current.play_id is not None:
            if mark_skipped:
                await self.history.skipped(current.play_id, position)
                current.play_id = None
            else:
                await self.history.progress(current.play_id, position)
        if active:
            await self._panic_locked()
        self._run_anchor_clock = None
        self._active_duration_seconds = None
        if reset_position:
            self._position_seconds = 0.0

    async def _panic_locked(self) -> None:
        async with self._send_lock:
            await self.router.panic()

    def _build_dispatches(
        self,
        timeline: MidiTimeline,
        plan: RoutingPlan | None,
    ) -> tuple[_Dispatch, ...]:
        dispatches: list[_Dispatch] = []
        for event in timeline.events:
            routed = self.router.route_message(event.message, plan=plan)
            if routed is None:
                continue
            dispatches.append(
                _Dispatch(
                    musical_at=event.at_seconds,
                    send_at=event.at_seconds + routed.latency_seconds,
                    routed=routed,
                )
            )
        dispatches.sort(key=lambda value: value.send_at)
        return tuple(dispatches)

    async def _begin_current_locked(self, *, start_position: float) -> None:
        current = self._current_item_locked()
        if current is None:
            raise PlaybackConflict("there is no current queue item")
        if not self.router.ready:
            raise PlaybackOutputError("no MIDI output is available")
        if current.play_id is None:
            current.play_id = await self.history.queued(
                asset_id=current.spec.asset_id,
                composition_id=current.spec.composition_id,
                duration_seconds=current.spec.duration_seconds,
            )
        try:
            timeline = MidiTimeline.from_file(Path(current.spec.midi_path))
            dispatches = self._build_dispatches(timeline, current.spec.routing_plan)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            await self.history.failed(current.play_id, start_position, error)
            current.play_id = None
            self._state = "stopped"
            self.events.publish(
                "error",
                {
                    "code": "internal_error",
                    "message": "Playback could not start. Check the server log.",
                    "detail": {"asset_id": current.spec.asset_id},
                },
            )
            raise PlaybackError(error) from exc
        await self.history.started(current.play_id)
        self._generation += 1
        generation = self._generation
        self._position_seconds = min(max(0.0, start_position), timeline.duration_seconds)
        self._active_duration_seconds = timeline.duration_seconds
        self._run_anchor_clock = self.clock.now()
        self._state = "playing"
        self._worker = asyncio.create_task(
            self._run_track(
                generation,
                current,
                timeline,
                dispatches,
                self._position_seconds,
                self._run_anchor_clock,
            ),
            name=f"openorchestrion:{current.spec.asset_id[:24]}",
        )
        self.events.publish("state.playback", self._playback_snapshot_locked().to_dict())

    async def _run_track(
        self,
        generation: int,
        item: RuntimeQueueItem,
        timeline: MidiTimeline,
        dispatches: tuple[_Dispatch, ...],
        start_position: float,
        anchor_clock: float,
    ) -> None:
        try:
            if start_position > 0:
                for message in timeline.priming_messages(start_position):
                    routed = self.router.route_message(message, plan=item.spec.routing_plan)
                    if routed is None:
                        continue
                    async with self._send_lock:
                        if generation != self._generation:
                            return
                        await routed.output.send(routed.message)

            threshold = (
                min(
                    timeline.duration_seconds,
                    min(60.0, max(15.0, timeline.duration_seconds * 0.5)),
                )
                if timeline.duration_seconds > 0
                else 0.0
            )
            threshold_pending = threshold > start_position
            relevant = [
                value for value in dispatches if value.musical_at + 1e-9 >= start_position
            ]
            index = 0
            completion_at = timeline.duration_seconds
            if relevant:
                completion_at = max(completion_at, max(value.send_at for value in relevant))

            while index < len(relevant) or threshold_pending:
                next_dispatch = (
                    relevant[index].send_at if index < len(relevant) else float("inf")
                )
                next_threshold = threshold if threshold_pending else float("inf")
                target = min(next_dispatch, next_threshold)
                await self.clock.sleep_until(
                    anchor_clock + max(0.0, target - start_position)
                )
                if generation != self._generation:
                    return
                if threshold_pending and next_threshold <= target + 1e-9:
                    if item.play_id is not None:
                        await self.history.progress(item.play_id, threshold)
                    threshold_pending = False
                while index < len(relevant) and relevant[index].send_at <= target + 1e-9:
                    dispatch = relevant[index]
                    async with self._send_lock:
                        if generation != self._generation:
                            return
                        await dispatch.routed.output.send(dispatch.routed.message)
                    index += 1

            await self.clock.sleep_until(
                anchor_clock + max(0.0, completion_at - start_position)
            )
            if generation != self._generation:
                return
            await self._complete_from_worker(generation, item, timeline.duration_seconds)
        except asyncio.CancelledError:
            return
        except Exception as exc:
            await self._fail_from_worker(generation, item, exc)

    async def _complete_from_worker(
        self,
        generation: int,
        item: RuntimeQueueItem,
        duration_seconds: float,
    ) -> None:
        async with self._lock:
            if generation != self._generation or item is not self._current_item_locked():
                return
            self._worker = None
            self._position_seconds = duration_seconds
            self._run_anchor_clock = None
            if item.play_id is not None:
                await self.history.completed(item.play_id, duration_seconds)
                item.play_id = None
            await self._panic_locked()
            if self._current_index is not None and self._current_index + 1 < len(self._queue):
                self._current_index += 1
                self._position_seconds = 0.0
                self._active_duration_seconds = None
                self.events.publish("state.queue", self._queue_snapshot_locked().to_dict())
                await self._begin_current_locked(start_position=0.0)
            else:
                self._state = "stopped"
                self._active_duration_seconds = duration_seconds
                self.events.publish(
                    "state.playback", self._playback_snapshot_locked().to_dict()
                )

    async def _fail_from_worker(
        self,
        generation: int,
        item: RuntimeQueueItem,
        exc: Exception,
    ) -> None:
        async with self._lock:
            if generation != self._generation or item is not self._current_item_locked():
                return
            self._worker = None
            position = self._position_now_locked()
            self._run_anchor_clock = None
            self._state = "stopped"
            error = f"{type(exc).__name__}: {exc}"
            if item.play_id is not None:
                await self.history.failed(item.play_id, position, error)
                item.play_id = None
            with suppress(Exception):
                await self._panic_locked()
            self.events.publish(
                "error",
                {
                    "code": "internal_error",
                    "message": "Playback stopped because a MIDI output or asset failed.",
                    "detail": {"asset_id": item.spec.asset_id},
                },
            )
            self.events.publish(
                "state.playback", self._playback_snapshot_locked().to_dict()
            )

    async def close(self) -> None:
        async with self._lock:
            if self._closed:
                return
            self._closed = True
            self._generation += 1
            if self._worker is not None and not self._worker.done():
                self._worker.cancel()
            self._worker = None
            with suppress(Exception):
                await self._panic_locked()
            await self.router.close()
