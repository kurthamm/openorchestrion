import json
from pathlib import Path

from mido import Message, MidiFile, MidiTrack

from openorchestrion.library.importer import discover_midi_files, import_midi


def _write_midi(path: Path, note: int = 60) -> None:
    midi = MidiFile(type=1, ticks_per_beat=480)
    track = MidiTrack()
    track.append(Message("note_on", channel=0, note=note, velocity=90, time=0))
    track.append(Message("note_off", channel=0, note=note, velocity=0, time=480))
    midi.tracks.append(track)
    midi.save(path)


def test_import_creates_content_addressed_asset_and_sidecar(tmp_path: Path) -> None:
    source = tmp_path / "example.mid"
    library = tmp_path / "library"
    _write_midi(source)

    result = import_midi(source, library)
    assert result.created is True
    assert Path(result.midi_path).exists()
    assert Path(result.metadata_path).exists()
    assert Path(result.midi_path).stem == result.asset_id

    sidecar = json.loads(Path(result.metadata_path).read_text())
    assert sidecar["asset_id"] == f"sha256:{result.asset_id}"
    assert sidecar["provenance"]["rights_status"] == "personal"
    assert sidecar["deterministic_analysis"]["note_count"] == 1
    assert sidecar["descriptive_metadata"] == {}
    assert sidecar["ai_enrichment"] == []
    assert not sidecar["deterministic_analysis"]["source"].startswith("/")


def test_reimport_is_idempotent(tmp_path: Path) -> None:
    source = tmp_path / "same.mid"
    library = tmp_path / "library"
    _write_midi(source)

    first = import_midi(source, library)
    second = import_midi(source, library)
    assert first.asset_id == second.asset_id
    assert second.created is False


def test_discovery_is_recursive_and_midi_only(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    _write_midi(tmp_path / "one.mid", 60)
    _write_midi(nested / "two.midi", 64)
    (nested / "ignore.txt").write_text("not midi")

    files = discover_midi_files([tmp_path])
    assert sorted(path.name for path in files) == ["one.mid", "two.midi"]
