from __future__ import annotations

import hashlib
import json
import sqlite3
import warnings
import zipfile
from pathlib import Path

import pytest

from openorchestrion.backup import BackupError, RestoreError, create_backup, restore_backup
from openorchestrion.history import (
    history_summaries,
    mark_completed,
    mark_started,
    queue_play,
)
from openorchestrion.library.catalog import get_asset, rebuild_catalog
from openorchestrion.library.importer import import_midi
from openorchestrion.library.metadata import read_metadata, update_metadata
from openorchestrion.testing.midi_fixtures import generate_suite


@pytest.fixture
def populated_state(tmp_path: Path) -> tuple[Path, str]:
    state = tmp_path / "state"
    library = state / "library"
    fixtures = tmp_path / "fixtures"
    generate_suite(fixtures, long_run_minutes=1)

    imported = import_midi(fixtures / "single-note.mid", library)
    asset_id = f"sha256:{imported.asset_id}"
    update_metadata(
        library,
        asset_id,
        {
            "title": "Backup Test Piece",
            "composer": "OpenOrchestrion",
            "genres": ["test"],
            "favorite": True,
        },
    )

    # AI enrichment is a separate durable block which the metadata writer
    # deliberately does not own. Seed one entry to prove backup is byte-level,
    # not a lossy reserialization of fields known to this module.
    sidecar = Path(imported.metadata_path)
    document = json.loads(sidecar.read_text(encoding="utf-8"))
    document["ai_enrichment"] = [
        {"provider": "test-model", "tags": ["gentle"], "confidence": 0.8}
    ]
    sidecar.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    rebuild_catalog(library)

    history = state / "history.db"
    play_id = queue_play(
        history,
        asset_id=asset_id,
        composition_id="composition:test",
        track_duration_seconds=20,
        occurred_at="2026-08-24T12:00:00+00:00",
    )
    mark_started(history, play_id, occurred_at="2026-08-24T12:00:01+00:00")
    mark_completed(
        history,
        play_id,
        occurred_at="2026-08-24T12:00:20+00:00",
        played_seconds=20,
    )
    return state, asset_id


def _rewrite_zip(
    source: Path,
    destination: Path,
    replacements: dict[str, bytes],
) -> None:
    with zipfile.ZipFile(source, "r") as old, zipfile.ZipFile(
        destination, "w", compression=zipfile.ZIP_DEFLATED
    ) as new:
        for info in old.infolist():
            payload = replacements.get(info.filename, old.read(info.filename))
            new.writestr(info.filename, payload)


def _manifest(path: Path) -> dict:
    with zipfile.ZipFile(path, "r") as archive:
        return json.loads(archive.read("manifest.json"))


def test_backup_restore_round_trip_preserves_durable_state_and_rebuilds_catalog(
    populated_state: tuple[Path, str], tmp_path: Path
) -> None:
    state, asset_id = populated_state
    archive = tmp_path / "backup.oo-backup.zip"
    before_sidecar = next((state / "library" / "assets").glob("*.json")).read_bytes()
    before_midi = next((state / "library" / "assets").glob("*.mid")).read_bytes()

    result = create_backup(state, archive)

    assert result.asset_count == 1
    assert result.history_included is True
    assert archive.is_file()
    with zipfile.ZipFile(archive, "r") as backup:
        names = set(backup.namelist())
    assert "history.db" in names
    assert "manifest.json" in names
    assert not any(name.endswith("catalog.db") for name in names)

    restored = tmp_path / "restored"
    restore = restore_backup(archive, restored)

    assert restore.asset_count == 1
    assert restore.history_restored is True
    assert Path(restore.catalog_path).is_file()
    assert next((restored / "library" / "assets").glob("*.mid")).read_bytes() == before_midi
    assert next((restored / "library" / "assets").glob("*.json")).read_bytes() == before_sidecar

    metadata = read_metadata(restored / "library", asset_id)
    assert metadata.descriptive_metadata["favorite"] is True
    assert metadata.descriptive_metadata["title"] == "Backup Test Piece"
    restored_document = json.loads(next((restored / "library" / "assets").glob("*.json")).read_text())
    assert restored_document["ai_enrichment"][0]["tags"] == ["gentle"]
    assert restored_document["provenance"] == json.loads(before_sidecar)["provenance"]

    indexed = get_asset(restored / "library" / "catalog.db", asset_id)
    assert indexed is not None
    assert indexed["title"] == "Backup Test Piece"
    assert indexed["favorite"] is True

    summaries = history_summaries(restored / "history.db", asset_ids=[asset_id])
    assert len(summaries) == 1
    assert summaries[0].completed_count == 1
    assert summaries[0].qualifying_play_count == 1


def test_history_snapshot_is_consistent_while_wal_connection_remains_open(
    populated_state: tuple[Path, str], tmp_path: Path
) -> None:
    state, asset_id = populated_state
    history = state / "history.db"

    live = sqlite3.connect(history)
    try:
        live.execute("PRAGMA journal_mode=WAL")
        assert live.execute("SELECT COUNT(*) FROM play_attempts").fetchone()[0] == 1
        archive = tmp_path / "live.zip"
        create_backup(state, archive)
    finally:
        live.close()

    restored = tmp_path / "restored-live"
    restore_backup(archive, restored)
    summaries = history_summaries(restored / "history.db", asset_ids=[asset_id])
    assert summaries[0].completed_count == 1


def test_manifest_hashes_exact_archive_payloads(
    populated_state: tuple[Path, str], tmp_path: Path
) -> None:
    state, _ = populated_state
    archive = tmp_path / "manifest.zip"
    create_backup(state, archive)

    manifest = _manifest(archive)
    with zipfile.ZipFile(archive, "r") as backup:
        for entry in manifest["files"]:
            payload = backup.read(entry["path"])
            assert len(payload) == entry["size_bytes"]
            assert hashlib.sha256(payload).hexdigest() == entry["sha256"]


def test_corrupted_content_addressed_source_refuses_backup(
    populated_state: tuple[Path, str], tmp_path: Path
) -> None:
    state, _ = populated_state
    midi = next((state / "library" / "assets").glob("*.mid"))
    payload = bytearray(midi.read_bytes())
    payload[-1] ^= 0x01
    midi.write_bytes(payload)

    with pytest.raises(BackupError, match="hashes to"):
        create_backup(state, tmp_path / "bad.zip")


def test_orphan_midi_refuses_backup(populated_state: tuple[Path, str], tmp_path: Path) -> None:
    state, _ = populated_state
    next((state / "library" / "assets").glob("*.json")).unlink()

    with pytest.raises(BackupError, match="missing sidecar"):
        create_backup(state, tmp_path / "orphan.zip")


def test_failed_backup_does_not_replace_previous_good_archive(
    populated_state: tuple[Path, str], tmp_path: Path
) -> None:
    state, _ = populated_state
    destination = tmp_path / "durable.zip"
    create_backup(state, destination)
    before = destination.read_bytes()

    next((state / "library" / "assets").glob("*.json")).unlink()
    with pytest.raises(BackupError):
        create_backup(state, destination)

    assert destination.read_bytes() == before


def test_tampered_archive_payload_is_rejected_without_partial_restore(
    populated_state: tuple[Path, str], tmp_path: Path
) -> None:
    state, _ = populated_state
    archive = tmp_path / "original.zip"
    create_backup(state, archive)
    manifest = _manifest(archive)
    midi_name = next(entry["path"] for entry in manifest["files"] if entry["path"].endswith(".mid"))
    with zipfile.ZipFile(archive, "r") as source:
        payload = bytearray(source.read(midi_name))
    payload[-1] ^= 0x01
    tampered = tmp_path / "tampered.zip"
    _rewrite_zip(archive, tampered, {midi_name: bytes(payload)})

    target = tmp_path / "restore-tampered"
    with pytest.raises(RestoreError, match="digest/size mismatch"):
        restore_backup(tampered, target)
    assert not target.exists()
    assert not list(tmp_path.glob(".restore-tampered.restore.*"))


def test_path_traversal_member_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "traversal.zip"
    manifest = {
        "format": "openorchestrion-application-data",
        "version": 1,
        "created_at": "2026-08-24T00:00:00+00:00",
        "asset_count": 0,
        "history_included": False,
        "files": [],
    }
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("manifest.json", json.dumps(manifest))
        output.writestr("../escape", b"nope")

    target = tmp_path / "restore"
    with pytest.raises(RestoreError, match="unsafe archive member"):
        restore_backup(archive, target)
    assert not target.exists()
    assert not (tmp_path / "escape").exists()


def test_duplicate_members_are_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "duplicates.zip"
    manifest = {
        "format": "openorchestrion-application-data",
        "version": 1,
        "created_at": "2026-08-24T00:00:00+00:00",
        "asset_count": 0,
        "history_included": False,
        "files": [],
    }
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("manifest.json", json.dumps(manifest))
            output.writestr("manifest.json", json.dumps(manifest))

    with pytest.raises(RestoreError, match="duplicate member"):
        restore_backup(archive, tmp_path / "restore")


def test_unsupported_manifest_version_is_rejected(
    populated_state: tuple[Path, str], tmp_path: Path
) -> None:
    state, _ = populated_state
    archive = tmp_path / "original.zip"
    create_backup(state, archive)
    manifest = _manifest(archive)
    manifest["version"] = 99
    bad = tmp_path / "version.zip"
    _rewrite_zip(archive, bad, {"manifest.json": json.dumps(manifest).encode()})

    with pytest.raises(RestoreError, match="unsupported backup version"):
        restore_backup(bad, tmp_path / "restore")


def test_non_empty_restore_target_is_refused_before_extraction(
    populated_state: tuple[Path, str], tmp_path: Path
) -> None:
    state, _ = populated_state
    archive = tmp_path / "backup.zip"
    create_backup(state, archive)
    target = tmp_path / "existing"
    target.mkdir()
    sentinel = target / "keep.txt"
    sentinel.write_text("keep")

    with pytest.raises(RestoreError, match="absent or empty"):
        restore_backup(archive, target)
    assert sentinel.read_text() == "keep"


def test_empty_existing_target_is_published_atomically(
    populated_state: tuple[Path, str], tmp_path: Path
) -> None:
    state, _ = populated_state
    archive = tmp_path / "backup.zip"
    create_backup(state, archive)
    target = tmp_path / "empty"
    target.mkdir()

    restore_backup(archive, target)

    assert (target / "library" / "catalog.db").is_file()
    assert not list(tmp_path.glob(".empty.restore.*"))
