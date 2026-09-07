from __future__ import annotations

from openorchestrion.midi.devices import is_kernel_loopback_port, list_output_ports
from openorchestrion.player_state import PlayerStateStore

from .clock import SystemClock
from .history_adapter import SqliteHistoryRecorder
from .outputs import MidiOutputRouter, MidoMidiOutput, VirtualMidiOutput
from .routed_engine import PlaybackEngine


def create_default_playback(settings: object) -> PlaybackEngine:
    """Build the production playback service without opening hardware ports yet."""
    clock = SystemClock()
    outputs = []
    try:
        # The kernel's Midi Through loopback is always listed and is never an
        # instrument. Treating it as an output let capability-aware routing send
        # part of an orchestral file to a port nobody hears.
        # A unique sequencer client name per output lets the hot-plug monitor
        # verify this process's own subscription in /proc/asound/seq/clients.
        outputs.extend(
            MidoMidiOutput(name, client_name=f"openorchestrion-{index}")
            for index, name in enumerate(list_output_ports())
            if not is_kernel_loopback_port(name)
        )
    except Exception:
        # Missing ALSA/rtmidi is a normal degraded state on a development machine.
        pass

    virtual_enabled = bool(getattr(settings, "virtual_midi", False))
    virtual_name = "OpenOrchestrion Virtual"
    if virtual_enabled:
        outputs.append(VirtualMidiOutput(virtual_name, clock))

    default_device = virtual_name if virtual_enabled else (outputs[0].name if outputs else None)
    router = MidiOutputRouter(outputs, default_device=default_device, allow_sysex=False)
    history = SqliteHistoryRecorder(settings.history_db, clock)
    state_path = getattr(settings, "player_state_db", None)
    state_store = PlayerStateStore(state_path) if state_path is not None else None
    return PlaybackEngine(router=router, history=history, clock=clock, state_store=state_store)
