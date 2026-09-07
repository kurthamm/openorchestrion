"""A queue request without rendering gets automatic voicing for orchestral score exports."""

from __future__ import annotations

import hashlib
from pathlib import Path

import mido
from fastapi.testclient import TestClient
from mido import Message, MetaMessage, MidiFile, MidiTrack

from openorchestrion.api.settings import Settings
from openorchestrion.app import create_app
from openorchestrion.library.catalog import rebuild_catalog
from openorchestrion.library.importer import import_paths
from openorchestrion.playback import RenderingMode


def _write(path: Path, parts: dict[int, tuple[str, int | None]]) -> str:
    """parts: {channel: (track name, program or None)}. Returns the asset id."""
    midi = MidiFile(type=1, ticks_per_beat=480)
    meta = MidiTrack()
    meta.append(MetaMessage("set_tempo", tempo=mido.bpm2tempo(120), time=0))
    midi.tracks.append(meta)
    for channel, (name, program) in parts.items():
        track = MidiTrack()
        track.append(MetaMessage("track_name", name=name, time=0))
        if program is not None:
            track.append(Message("program_change", channel=channel, program=program, time=0))
        for index in range(4):
            track.append(Message("note_on", channel=channel, note=60 + index, velocity=80, time=0))
            track.append(Message("note_off", channel=channel, note=60 + index, velocity=0, time=480))
        midi.tracks.append(track)
    midi.save(path)
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _client(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    orchestra = _write(
        src / "symphony.mid",
        {1: ("Flute", 73), 2: ("Oboe", 68), 3: ("Clarinet", 71), 4: ("Bassoon", 70), 5: ("Corno", 69),
         7: ("Timpani", 47), 8: ("Violino I", 40), 10: ("Violino II", 40), 11: ("Viola", 41), 12: ("Cello", 42)},
    )
    piano = _write(src / "sonata.mid", {0: ("right", 0), 1: ("left", 0)})
    root = tmp_path / "library"
    assert not import_paths([src], root).failed
    rebuild_catalog(root)
    settings = Settings(library_root=root, catalog_db=root / "catalog.db", history_db=root / "history.db", virtual_midi=True)
    return TestClient(create_app(settings=settings)), orchestra, piano


def _policies(client: TestClient):
    engine = client.app.state.playback
    return [item.spec.rendering_policy for item in engine._queue]  # noqa: SLF001 - rendering is not in the public queue model


def test_orchestral_export_is_re_voiced_by_default(tmp_path: Path) -> None:
    client, orchestra, piano = _client(tmp_path)
    with client:
        response = client.post("/api/queue", json={"asset_ids": [orchestra, piano]})
        assert response.status_code == 200, response.text
        orchestral_policy, piano_policy = _policies(client)

    assert orchestral_policy is not None
    assert orchestral_policy.mode is RenderingMode.OVERRIDE
    overrides = {o.channel: o.program for o in orchestral_policy.program_overrides}
    assert overrides == {5: 60, 8: 48, 10: 48, 11: 48, 12: 48}
    assert piano_policy is None, "a piano file keeps its source arrangement"


def test_explicit_original_rendering_disables_the_correction(tmp_path: Path) -> None:
    client, orchestra, _ = _client(tmp_path)
    with client:
        response = client.post("/api/queue", json={"asset_ids": [orchestra], "rendering": {"mode": "ORIGINAL"}})
        assert response.status_code == 200, response.text
        (policy,) = _policies(client)
    assert policy is not None and policy.mode is RenderingMode.ORIGINAL and policy.program_overrides == ()
