"""Master volume: scaled Channel Volume on every output, never velocity."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import mido
import pytest
from fastapi.testclient import TestClient
from mido import Message, MetaMessage, MidiFile, MidiTrack

from openorchestrion.api.settings import Settings
from openorchestrion.app import create_app
from openorchestrion.playback import ManualClock, MidiOutputRouter, PlaybackEngine, QueueItemSpec, VirtualMidiOutput


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


def _write_midi(path: Path, *, cc7: int | None = 127) -> float:
    midi = MidiFile(type=1, ticks_per_beat=480)
    meta = MidiTrack()
    meta.append(MetaMessage("set_tempo", tempo=mido.bpm2tempo(120), time=0))
    midi.tracks.append(meta)
    track = MidiTrack()
    if cc7 is not None:
        track.append(Message("control_change", channel=0, control=7, value=cc7, time=0))
    for index in range(4):
        track.append(Message("note_on", channel=0, note=60 + index, velocity=90, time=0))
        track.append(Message("note_off", channel=0, note=60 + index, velocity=0, time=480))
    midi.tracks.append(track)
    midi.save(path)
    return MidiFile(path).length


async def _engine():
    clock = ManualClock()
    output = VirtualMidiOutput("Keyboard", clock)
    engine = PlaybackEngine(router=MidiOutputRouter([output], default_device="Keyboard"), history=FakeHistory(), clock=clock)
    return engine, clock, output


def _cc7(output, channel=None):
    return [
        (e.message.channel, e.message.value)
        for e in output.sent
        if e.message.type == "control_change" and e.message.control == 7 and (channel is None or e.message.channel == channel)
    ]


@pytest.mark.asyncio
async def test_default_volume_sends_channel_volume_100_on_every_channel(tmp_path: Path) -> None:
    midi = tmp_path / "a.mid"
    duration = _write_midi(midi, cc7=None)
    engine, clock, output = await _engine()
    await engine.set_queue([QueueItemSpec("a", "A", duration, str(midi))])
    await engine.transport("play")
    await clock.advance(duration + 0.01)
    assert (await engine.playback_snapshot()).volume == 100
    first_note = next(i for i, e in enumerate(output.sent) if e.message.type == "note_on")
    before = [(e.message.channel, e.message.value) for e in output.sent[:first_note] if e.message.type == "control_change" and e.message.control == 7]
    assert sorted(before) == [(ch, 100) for ch in range(16)]


@pytest.mark.asyncio
async def test_file_channel_volume_is_scaled_and_velocity_is_not(tmp_path: Path) -> None:
    midi = tmp_path / "a.mid"
    duration = _write_midi(midi, cc7=127)
    engine, clock, output = await _engine()
    snapshot = await engine.set_volume(50)
    assert snapshot.volume == 50
    assert _cc7(output, channel=0)[-1] == (0, 50), "idle set_volume applies the default base of 100 scaled"
    await engine.set_queue([QueueItemSpec("a", "A", duration, str(midi))])
    await engine.transport("play")
    await clock.advance(0.01)
    assert _cc7(output, channel=0)[-1] == (0, 64), "the file's CC7 127 scaled by 50%"
    velocities = {e.message.velocity for e in output.sent if e.message.type == "note_on" and e.message.velocity}
    assert velocities == {90}


@pytest.mark.asyncio
async def test_changing_volume_mid_track_resends_from_the_file_base(tmp_path: Path) -> None:
    midi = tmp_path / "a.mid"
    duration = _write_midi(midi, cc7=127)
    engine, clock, output = await _engine()
    await engine.set_queue([QueueItemSpec("a", "A", duration, str(midi))])
    await engine.transport("play")
    await clock.advance(0.5)
    before = len(output.sent)
    await engine.set_volume(25)
    sent = [(e.message.channel, e.message.value) for e in output.sent[before:] if e.message.type == "control_change" and e.message.control == 7]
    assert (0, 32) in sent, "channel 0 uses the file's base 127 -> 32 at 25%"
    assert (1, 25) in sent, "channels the file never set use base 100 -> 25"
    assert len(sent) == 16


@pytest.mark.asyncio
async def test_volume_range_and_idempotent_command() -> None:
    engine, _, output = await _engine()
    with pytest.raises(ValueError):
        await engine.set_volume(101)
    with pytest.raises(ValueError):
        await engine.set_volume(-1)
    await engine.set_volume(40, command_id="c1")
    sent = len(output.sent)
    again = await engine.set_volume(40, command_id="c1")
    assert again.volume == 40 and len(output.sent) == sent


def test_volume_api(tmp_path: Path) -> None:
    settings = Settings(library_root=tmp_path / "lib", catalog_db=tmp_path / "lib" / "catalog.db", history_db=tmp_path / "h.db", virtual_midi=True)
    with TestClient(create_app(settings=settings)) as client:
        assert client.get("/api/status").json()["phase"] in {"ready", "degraded"}
        response = client.post("/api/volume", json={"level": 30})
        assert response.status_code == 200, response.text
        assert response.json()["volume"] == 30
        assert client.post("/api/transport/stop", json={}).json()["volume"] == 30
        assert client.post("/api/volume", json={"level": 101}).status_code == 422
        assert client.post("/api/volume", json={"level": "50"}).status_code == 422
