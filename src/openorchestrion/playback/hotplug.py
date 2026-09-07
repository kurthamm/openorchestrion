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
from typing import Protocol

from openorchestrion.midi.devices import (
    client_link_targets,
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
    """Presence via the MIDI backend; subscription health via the ALSA sequencer table."""

    def is_connected(self, output: MidoMidiOutput) -> bool:
        available = list_output_ports()
        if resolve_output_port(output.name, available) is None:
            return False
        if output.port_name is None or output.client_name is None:
            # Not opened yet (or identity unknown): presence is all we can check.
            return True
        target = port_link_target(output.port_name)
        if target is None:
            return True
        table = read_sequencer_clients()
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
        self._outputs = tuple(
            output
            for output in engine.router.outputs.values()
            if isinstance(output, MidoMidiOutput)
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
        while True:
            try:
                await self.check_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("MIDI output hot-plug check failed; monitoring stopped")
                return
            await asyncio.sleep(self.interval_seconds)


__all__ = ["AlsaOutputLinkProbe", "OutputLinkMonitor", "OutputLinkProbe"]
