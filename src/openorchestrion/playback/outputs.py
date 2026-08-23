from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import mido
from mido import Message

from openorchestrion.midi.router import MidiRoute, RoutingPlan
from openorchestrion.models import DeviceProfile

from .clock import Clock


class PlaybackOutputError(RuntimeError):
    pass


class MidiOutput(Protocol):
    name: str

    async def send(self, message: Message) -> None: ...

    async def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class SentMidiMessage:
    at_seconds: float
    message: Message


class VirtualMidiOutput:
    """In-memory MIDI output used by tests and hardware-free development."""

    def __init__(
        self,
        name: str,
        clock: Clock,
        *,
        profile: DeviceProfile | None = None,
    ) -> None:
        self.name = name
        self.clock = clock
        self.profile = profile
        self.sent: list[SentMidiMessage] = []
        self.closed = False

    async def send(self, message: Message) -> None:
        if self.closed:
            raise PlaybackOutputError(f"MIDI output {self.name!r} is closed")
        self.sent.append(SentMidiMessage(self.clock.now(), message.copy(time=0)))

    async def close(self) -> None:
        self.closed = True


class MidoMidiOutput:
    """Lazy mido output wrapper so app startup does not seize hardware ports."""

    def __init__(self, name: str, *, profile: DeviceProfile | None = None) -> None:
        self.name = name
        self.profile = profile
        self._port = None

    async def send(self, message: Message) -> None:
        if self._port is None:
            self._port = mido.open_output(self.name)
        self._port.send(message)

    async def close(self) -> None:
        if self._port is not None:
            self._port.close()
            self._port = None


@dataclass(frozen=True, slots=True)
class RoutedMessage:
    output: MidiOutput
    message: Message
    latency_seconds: float
    destination_device: str


class MidiOutputRouter:
    def __init__(
        self,
        outputs: list[MidiOutput] | tuple[MidiOutput, ...],
        *,
        default_device: str | None = None,
        default_plan: RoutingPlan | None = None,
        allow_sysex: bool = False,
    ) -> None:
        self.outputs = {output.name: output for output in outputs}
        self.default_device = default_device or (next(iter(self.outputs), None))
        self.default_plan = default_plan
        self.allow_sysex = allow_sysex
        if self.default_device is not None and self.default_device not in self.outputs:
            raise PlaybackOutputError(f"unknown default MIDI output {self.default_device!r}")

    @property
    def ready(self) -> bool:
        return bool(self.outputs)

    @property
    def output_names(self) -> tuple[str, ...]:
        return tuple(self.outputs)

    def profile_for(self, output_name: str) -> DeviceProfile | None:
        output = self.outputs.get(output_name)
        if output is None:
            return None
        profile = getattr(output, "profile", None)
        return profile if isinstance(profile, DeviceProfile) else None

    def route_messages(
        self,
        message: Message,
        *,
        track_index: int | None = None,
        plan: RoutingPlan | None = None,
    ) -> tuple[RoutedMessage, ...]:
        """Route one source event to zero, one, or several output destinations."""
        if message.type == "sysex" and not self.allow_sysex:
            return ()

        active_plan = plan or self.default_plan
        channel = message.channel if hasattr(message, "channel") else None
        routes: tuple[MidiRoute, ...] = ()
        if active_plan is not None:
            routes = active_plan.destinations_for(channel, track_index)

        if not routes:
            if self.default_device is None:
                raise PlaybackOutputError("no MIDI output is available")
            routes = (
                MidiRoute(
                    source_channel=channel,
                    source_track=track_index,
                    destination_device=self.default_device,
                ),
            )

        routed_messages: list[RoutedMessage] = []
        seen: set[tuple[str, int | None, float]] = set()
        for route in routes:
            destination = route.destination_device
            output = self.outputs.get(destination)
            if output is None:
                if active_plan is not None and active_plan.failure_policy == "drop":
                    continue
                raise PlaybackOutputError(
                    f"MIDI output disappeared or is not configured: {destination}"
                )

            latency = route.latency_offset_ms / 1000.0
            if latency < 0:
                raise PlaybackOutputError("negative latency offsets are not supported")
            destination_channel = route.destination_channel
            identity = (destination, destination_channel, latency)
            if identity in seen:
                continue
            seen.add(identity)

            routed = message.copy(time=0)
            if destination_channel is not None and hasattr(routed, "channel"):
                routed = routed.copy(channel=destination_channel)
            routed_messages.append(
                RoutedMessage(
                    output=output,
                    message=routed,
                    latency_seconds=latency,
                    destination_device=destination,
                )
            )
        return tuple(routed_messages)

    def route_message(
        self,
        message: Message,
        *,
        plan: RoutingPlan | None = None,
    ) -> RoutedMessage | None:
        """Backward-compatible single-destination routing helper."""
        routed = self.route_messages(message, plan=plan)
        return routed[0] if routed else None

    async def panic(self) -> None:
        """Release sustain and silence every channel on every configured output."""
        failures: list[str] = []
        for output in self.outputs.values():
            try:
                for channel in range(16):
                    await output.send(Message("control_change", channel=channel, control=64, value=0))
                    await output.send(Message("control_change", channel=channel, control=120, value=0))
                    await output.send(Message("control_change", channel=channel, control=123, value=0))
            except Exception as exc:
                # Continue cleanup on the other devices even if one output failed.
                failures.append(f"{output.name}: {type(exc).__name__}: {exc}")
        if failures:
            raise PlaybackOutputError("; ".join(failures))

    async def close(self) -> None:
        for output in self.outputs.values():
            await output.close()
