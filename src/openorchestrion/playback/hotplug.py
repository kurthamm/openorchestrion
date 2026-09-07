"""Hot-plug detection for physical MIDI outputs.

ALSA keeps a per-process subscription from our sequencer client to the
keyboard's port.  Unplugging the keyboard silently destroys that subscription;
events sent afterwards go nowhere and no error is raised, even once the device
is plugged back in.  The monitor polls for the device and, on Linux, for the
subscription itself, and tells the engine only when something changes.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Protocol

from openorchestrion.midi.devices import (
    SequencerClient,
    client_link_targets,
    is_kernel_loopback_port,
    list_output_ports,
    port_link_target,
    read_sequencer_clients,
    resolve_output_port,
)

from .outputs import MidoMidiOutput

log = logging.getLogger(__name__)


class OutputLinkProbe(Protocol):
    def is_connected(self, output: MidoMidiOutput) -> bool: ...


class AlsaOutputLinkProbe:
    """Presence via the MIDI backend; subscription health via the ALSA sequencer table.

    A closed output (``port_name`` is None) is judged on presence alone.  The
    engine closes an output's handle as soon as it is reported disconnected, so
    a device that returns under a new ALSA address is seen as present again and
    reopened by its stable base name on the next send.
    """

    def __init__(
        self,
        *,
        list_ports: Callable[[], list[str]] = list_output_ports,
        read_table: Callable[[], dict[int, SequencerClient] | None] = read_sequencer_clients,
    ) -> None:
        self._list_ports = list_ports
        self._read_table = read_table

    def is_connected(self, output: MidoMidiOutput) -> bool:
        available = self._list_ports()
        if resolve_output_port(output.name, available) is None:
            return False
        if output.port_name is None or output.client_name is None:
            # Not opened yet (or identity unknown): presence is all we can check.
            return True
        target = port_link_target(output.port_name)
        if target is None:
            return True
        table = self._read_table()
        if table is None:
            return True
        return target in client_link_targets(table, output.client_name)


class OutputLinkMonitor:
    """Poll the probe and report link transitions to the playback engine."""

    def __init__(
        self,
        engine,
        probe: OutputLinkProbe,
        *,
        interval_seconds: float = 1.0,
    ) -> None:
        self.engine = engine
        self.probe = probe
        self.interval_seconds = interval_seconds
        # Only real hardware is monitored: the kernel's Midi Through loopback
        # can never be unplugged and would only add noise.
        self._outputs = tuple(
            output
            for output in engine.router.outputs.values()
            if isinstance(output, MidoMidiOutput) and not is_kernel_loopback_port(output.name)
        )
        self._connected: dict[str, bool] = {}
        self._task: asyncio.Task[None] | None = None

    @property
    def monitored_outputs(self) -> tuple[str, ...]:
        return tuple(output.name for output in self._outputs)

    async def check_once(self) -> None:
        for output in self._outputs:
            connected = self.probe.is_connected(output)
            previous = self._connected.get(output.name)
            self._connected[output.name] = connected
            if previous is None and connected:
                continue
            if previous == connected:
                continue
            await self.engine.output_link_changed(output.name, connected=connected)

    async def start(self) -> None:
        if not self._outputs or self._task is not None:
            return
        self._task = asyncio.create_task(self._run(), name="openorchestrion:hotplug")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _run(self) -> None:
        failing = False
        while True:
            try:
                await self.check_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                # A transient enumeration failure must not end monitoring for
                # the life of the process. Log the first failure of a streak;
                # later ticks retry quietly until a probe succeeds again.
                if not failing:
                    log.exception("MIDI output hot-plug check failed; retrying")
                failing = True
            else:
                if failing:
                    log.info("MIDI output hot-plug check recovered")
                failing = False
            await asyncio.sleep(self.interval_seconds)


__all__ = ["AlsaOutputLinkProbe", "OutputLinkMonitor", "OutputLinkProbe"]
