"""Hot-plug detection and recovery for physical MIDI outputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import partial
from pathlib import Path

import mido
import pytest
from mido import Message, MetaMessage, MidiFile, MidiTrack

from openorchestrion.midi.devices import (
    client_link_targets,
    parse_sequencer_clients,
    port_base_name,
    port_link_target,
    resolve_output_port,
)
from openorchestrion.playback import (
    MidiOutputRouter,
    PlaybackEngine,
    PlaybackOutputError,
    QueueItemSpec,
    VirtualMidiOutput,
)
from openorchestrion.playback.hotplug import OutputLinkMonitor
from openorchestrion.playback.outputs import MidoMidiOutput
from openorchestrion.playback import ManualClock

# Captured from a Raspberry Pi 5 with a Casio WK-220 while the service played.
SEQ_CLIENTS = """\
Client info
  cur  clients : 5
  peak clients : 6
  max  clients : 192
Client   0 : "System" [Kernel Legacy]
  Port   0 : "Timer" (Rwe-) [In/Out]
  Port   1 : "Announce" (R-e-) [In]
Client  14 : "Midi Through" [Kernel Legacy]
  Port   0 : "Midi Through Port-0" (RWe-) [In/Out]
    Connected From: 128:0[r:0]
Client  24 : "CASIO USB-MIDI" [Kernel Legacy]
  Port   0 : "CASIO USB-MIDI MIDI 1" (RWeX) [In/Out]
    Connected From: 129:0[r:0]
Client 128 : "openorchestrion-0" [User Legacy]
  Port   0 : "RtMidi output" (R-e-) [In]
    Connecting To: 14:0[r:0]
  Output pool :
    Pool size          : 500
    Cells in use       : 0
Client 129 : "openorchestrion-1" [User Legacy]
  Port   0 : "RtMidi output" (R-e-) [In]
    Connecting To: 24:0[r:0]
  Output pool :
    Pool size          : 500
"""


@dataclass
class FakeHistory:
    events: list[tuple] = field(default_factory=list)
    counter: int = 0

    async def queued(self, *, asset_id: str, composition_id: str | None, duration_seconds: float) -> str:
        self.counter += 1
        return f"p{self.counter}"

    async def started(self, play_id: str) -> None: ...
    async def progress(self, play_id: str, played_seconds: float) -> None: ...
    async def completed(self, play_id: str, played_seconds: float) -> None: ...
    async def skipped(self, play_id: str, played_seconds: float) -> None: ...
    async def failed(self, play_id: str, played_seconds: float, error: str) -> None: ...

CASIO = "CASIO USB-MIDI:CASIO USB-MIDI MIDI 1 24:0"


def test_port_names_split_into_stable_base_and_alsa_address() -> None:
    assert port_base_name(CASIO) == "CASIO USB-MIDI:CASIO USB-MIDI MIDI 1"
    assert port_link_target(CASIO) == (24, 0)
    assert port_base_name("OpenOrchestrion Virtual") == "OpenOrchestrion Virtual"
    assert port_link_target("OpenOrchestrion Virtual") is None


def test_resolve_output_port_follows_a_renumbered_device() -> None:
    available = ["Midi Through:Midi Through Port-0 14:0", "CASIO USB-MIDI:CASIO USB-MIDI MIDI 1 28:0"]
    assert resolve_output_port(CASIO, available) == "CASIO USB-MIDI:CASIO USB-MIDI MIDI 1 28:0"
    assert resolve_output_port(CASIO, ["Midi Through:Midi Through Port-0 14:0"]) is None


def test_sequencer_table_exposes_our_subscriptions() -> None:
    table = parse_sequencer_clients(SEQ_CLIENTS)
    assert table[24].name == "CASIO USB-MIDI"
    assert client_link_targets(table, "openorchestrion-1") == {(24, 0)}
    assert client_link_targets(table, "openorchestrion-0") == {(14, 0)}
    assert client_link_targets(table, "openorchestrion-9") == set()


def test_sequencer_table_after_unplug_has_no_subscription() -> None:
    unplugged = "\n".join(
        line for line in SEQ_CLIENTS.splitlines() if "24:0" not in line and "CASIO" not in line
    )
    table = parse_sequencer_clients(unplugged)
    assert 24 not in table
    assert client_link_targets(table, "openorchestrion-1") == set()


def _write_midi(path: Path, beats: int = 8) -> float:
    midi = MidiFile(type=1, ticks_per_beat=480)
    meta = MidiTrack()
    meta.append(MetaMessage("set_tempo", tempo=mido.bpm2tempo(120), time=0))
    midi.tracks.append(meta)
    track = MidiTrack()
    for index in range(beats):
        track.append(Message("note_on", channel=0, note=60 + index, velocity=90, time=0))
        track.append(Message("note_off", channel=0, note=60 + index, velocity=0, time=480))
    midi.tracks.append(track)
    midi.save(path)
    return MidiFile(path).length


class _ClosableOutput(VirtualMidiOutput):
    """Virtual output that records close() calls, mirroring the lazy hardware port."""

    def __init__(self, name: str, clock: ManualClock) -> None:
        super().__init__(name, clock)
        self.close_calls = 0

    async def close(self) -> None:
        self.close_calls += 1
        # A hardware output reopens lazily on the next send; keep this one usable.


async def _engine():
    clock = ManualClock()
    output = _ClosableOutput("Keyboard", clock)
    router = MidiOutputRouter([output], default_device="Keyboard")
    engine = PlaybackEngine(router=router, history=FakeHistory(), clock=clock)
    return engine, clock, output


@pytest.mark.asyncio
async def test_disconnect_pauses_and_reconnect_resumes_from_position(tmp_path: Path) -> None:
    midi = tmp_path / "long.mid"
    duration = _write_midi(midi)
    engine, clock, output = await _engine()
    events = engine.events.subscribe()
    await engine.set_queue([QueueItemSpec("a", "A", duration, str(midi))])
    await engine.transport("play")
    await clock.advance(1.0)

    await engine.output_link_changed("Keyboard", connected=False)

    snapshot = await engine.playback_snapshot()
    assert snapshot.state == "paused"
    assert 900 <= snapshot.position.position_ms <= 1100
    assert engine.outputs_ready is False
    assert engine.outputs_state() == {
        "ready": False,
        "devices": ["Keyboard"],
        "reason": "output_disconnected",
    }
    sent_while_unplugged = len(output.sent)
    await clock.advance(2.0)
    assert len(output.sent) == sent_while_unplugged

    with pytest.raises(PlaybackOutputError):
        await engine.transport("play")

    await engine.output_link_changed("Keyboard", connected=True)

    assert output.close_calls == 1, "the stale hardware port must be dropped so it reopens"
    resumed = await engine.playback_snapshot()
    assert resumed.state == "playing"
    assert 900 <= resumed.position.position_ms <= 1100
    assert engine.outputs_ready is True
    assert engine.outputs_state()["reason"] is None
    await clock.advance(duration)
    assert (await engine.playback_snapshot()).state == "stopped"

    types = []
    while not events.empty():
        types.append(events.get_nowait().type)
    assert types.count("state.devices") >= 2
    assert "state.playback" in types


@pytest.mark.asyncio
async def test_reconnect_does_not_resume_a_user_pause(tmp_path: Path) -> None:
    midi = tmp_path / "long.mid"
    duration = _write_midi(midi)
    engine, clock, _ = await _engine()
    await engine.set_queue([QueueItemSpec("a", "A", duration, str(midi))])
    await engine.transport("play")
    await clock.advance(0.5)
    await engine.transport("pause")

    await engine.output_link_changed("Keyboard", connected=False)
    await engine.output_link_changed("Keyboard", connected=True)

    assert (await engine.playback_snapshot()).state == "paused"


@pytest.mark.asyncio
async def test_disconnect_while_stopped_only_reports(tmp_path: Path) -> None:
    engine, _, _ = await _engine()
    await engine.output_link_changed("Keyboard", connected=False)
    assert engine.outputs_state()["reason"] == "output_disconnected"
    assert (await engine.playback_snapshot()).state == "idle"
    await engine.output_link_changed("Keyboard", connected=True)
    assert engine.outputs_state()["ready"] is True


@pytest.mark.asyncio
async def test_unknown_output_is_rejected() -> None:
    engine, _, _ = await _engine()
    with pytest.raises(ValueError):
        await engine.output_link_changed("Nope", connected=False)


class _FakeProbe:
    def __init__(self) -> None:
        self.connected: dict[str, bool] = {}

    def is_connected(self, output) -> bool:
        return self.connected[output.name]


class _RecordingEngine:
    def __init__(self, outputs) -> None:
        self.router = MidiOutputRouter(outputs)
        self.calls: list[tuple[str, bool]] = []

    async def output_link_changed(self, name: str, *, connected: bool) -> None:
        self.calls.append((name, connected))


@pytest.mark.asyncio
async def test_monitor_reports_only_transitions() -> None:
    clock = ManualClock()
    keyboard = MidoMidiOutput(CASIO, client_name="openorchestrion-1")
    virtual = VirtualMidiOutput("OpenOrchestrion Virtual", clock)
    engine = _RecordingEngine([keyboard, virtual])
    probe = _FakeProbe()
    monitor = OutputLinkMonitor(engine, probe, interval_seconds=1.0)

    probe.connected[CASIO] = True
    await monitor.check_once()
    assert engine.calls == []

    await monitor.check_once()
    assert engine.calls == []

    probe.connected[CASIO] = False
    await monitor.check_once()
    assert engine.calls == [(CASIO, False)]

    await monitor.check_once()
    assert engine.calls == [(CASIO, False)]

    probe.connected[CASIO] = True
    await monitor.check_once()
    assert engine.calls == [(CASIO, False), (CASIO, True)]
    assert monitor.monitored_outputs == (CASIO,)


@pytest.mark.asyncio
async def test_monitor_reports_a_device_missing_at_startup() -> None:
    keyboard = MidoMidiOutput(CASIO, client_name="openorchestrion-1")
    engine = _RecordingEngine([keyboard])
    probe = _FakeProbe()
    probe.connected[CASIO] = False
    monitor = OutputLinkMonitor(engine, probe, interval_seconds=1.0)
    await monitor.check_once()
    assert engine.calls == [(CASIO, False)]


def test_hardware_output_identity_survives_renumbering() -> None:
    output = MidoMidiOutput(CASIO, client_name="openorchestrion-1")
    assert output.name == CASIO
    assert output.base_name == "CASIO USB-MIDI:CASIO USB-MIDI MIDI 1"
    assert output.client_name == "openorchestrion-1"
    assert output.port_name is None


def test_status_api_reports_a_disconnected_output(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from openorchestrion.api.settings import Settings
    from openorchestrion.app import create_app

    clock = ManualClock()
    output = _ClosableOutput("Keyboard", clock)
    engine = PlaybackEngine(
        router=MidiOutputRouter([output], default_device="Keyboard"),
        history=FakeHistory(),
        clock=clock,
    )
    settings = Settings(
        library_root=tmp_path / "library",
        catalog_db=tmp_path / "library" / "catalog.db",
        history_db=tmp_path / "history.db",
    )
    with TestClient(create_app(settings=settings, playback=engine)) as client:
        assert client.get("/api/status").json()["outputs"] == {
            "ready": True,
            "devices": ["Keyboard"],
            "reason": None,
        }
        client.portal.call(partial(engine.output_link_changed, "Keyboard", connected=False))
        assert client.get("/api/status").json()["outputs"] == {
            "ready": False,
            "devices": ["Keyboard"],
            "reason": "output_disconnected",
        }
