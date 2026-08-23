from __future__ import annotations

import asyncio
from dataclasses import replace

from openorchestrion.midi.router import RoutingPlan

from .engine import PlaybackEngine as BasePlaybackEngine
from .engine import _Dispatch
from .models import RuntimeQueueItem
from .routing import RoutingDecision, RoutingEndpoint, plan_routing
from .timeline import MidiTimeline


class PlaybackEngine(BasePlaybackEngine):
    """Playback engine with track-aware, capability-aware multi-output routing."""

    def __init__(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        super().__init__(*args, **kwargs)
        self.last_routing_decision: RoutingDecision | None = None

    def _routing_endpoints(self) -> tuple[RoutingEndpoint, ...]:
        return tuple(
            RoutingEndpoint(
                output_name=name,
                profile=self.router.profile_for(name),
            )
            for name in self.router.output_names
        )

    async def _begin_current_locked(self, *, start_position: float) -> None:
        current = self._current_item_locked()
        if (
            current is not None
            and current.spec.routing_plan is None
            and len(self.router.output_names) > 1
        ):
            # Plan at play time rather than queue time so routing reflects the
            # outputs actually connected when the track begins.
            timeline = MidiTimeline.from_file(current.spec.midi_path)
            decision = plan_routing(
                timeline,
                self._routing_endpoints(),
                performance_type=current.spec.performance_type,
                device_preferences=current.spec.device_preferences,
                routing_preferences=current.spec.routing_preferences,
            )
            current.spec = replace(current.spec, routing_plan=decision.plan)
            self.last_routing_decision = decision
        await super()._begin_current_locked(start_position=start_position)

    def _build_dispatches(
        self,
        timeline: MidiTimeline,
        plan: RoutingPlan | None,
    ) -> tuple[_Dispatch, ...]:
        dispatches: list[_Dispatch] = []
        for event in timeline.events:
            for routed in self.router.route_messages(
                event.message,
                track_index=event.track_index,
                plan=plan,
            ):
                dispatches.append(
                    _Dispatch(
                        musical_at=event.at_seconds,
                        send_at=event.at_seconds + routed.latency_seconds,
                        routed=routed,
                    )
                )
        dispatches.sort(
            key=lambda value: (
                value.send_at,
                value.routed.destination_device.casefold(),
            )
        )
        return tuple(dispatches)

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
                for event in timeline.priming_events(start_position):
                    for routed in self.router.route_messages(
                        event.message,
                        track_index=event.track_index,
                        plan=item.spec.routing_plan,
                    ):
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
            # The base failure path records durable history and panics every
            # remaining output. We deliberately stop instead of silently moving
            # an independent piano/part to another sound engine.
            await self._fail_from_worker(generation, item, exc)
