import sqlite3
from pathlib import Path

import pytest

from openorchestrion.player_state import PlayerStateStore


def test_saved_playlists_stations_and_session_survive_reopening(tmp_path: Path) -> None:
    path = tmp_path / "player-state.db"
    store = PlayerStateStore(path)
    playlist = store.save_collection(name="Evening", kind="playlist", asset_ids=["a", "b"])
    station = store.save_collection(
        name="Quiet piano", kind="station", intent={"mode": "station", "moods": ["calm"]}
    )
    store.save_session({"queue": [{"asset_id": "a"}], "volume": 63})

    reopened = PlayerStateStore(path)
    assert reopened.get_collection(playlist.id).asset_ids == ("a", "b")
    assert reopened.get_collection(station.id).intent["moods"] == ["calm"]
    assert reopened.load_session()["volume"] == 63


def test_collections_can_be_renamed_and_deleted(tmp_path: Path) -> None:
    store = PlayerStateStore(tmp_path / "player-state.db")
    saved = store.save_collection(name="First", kind="playlist", asset_ids=["a"])
    assert store.rename_collection(saved.id, "Renamed").name == "Renamed"
    assert store.delete_collection(saved.id)
    assert store.get_collection(saved.id) is None


def test_collection_names_are_unique(tmp_path: Path) -> None:
    store = PlayerStateStore(tmp_path / "player-state.db")
    store.save_collection(name="Evening", kind="playlist", asset_ids=["a"])
    with pytest.raises(sqlite3.IntegrityError):
        store.save_collection(name="evening", kind="playlist", asset_ids=["b"])


def test_song_playback_preference_is_durable(tmp_path: Path) -> None:
    store = PlayerStateStore(tmp_path / "player-state.db")
    store.save_song_preference("asset", tempo_percent=85, volume_percent=110,
                               rendering={"mode": "PIANO_ONLY", "piano_program": 0, "program_overrides": []})
    value = PlayerStateStore(store.path).get_song_preference("asset")
    assert value["tempo_percent"] == 85
    assert value["volume_percent"] == 110
    assert value["rendering"]["mode"] == "PIANO_ONLY"
