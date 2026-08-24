from __future__ import annotations

import hashlib
import json
import sqlite3
import stat
import warnings
import zipfile
from pathlib import Path

import pytest

from openorchestrion.backup import BackupError, create_backup, restore_backup
from openorchestrion.history import (
    history_summaries,
    mark_completed,
    mark_started,
    queue_play,
)
from openorchestrion.library.catalog import catalog_stats, get_asset, rebuild_catalog
from openorchestrion.library.importer import import_midi
from openorchestrion.library.metadata import update_metadata
from openorchestrion.testing.midi_fixtures import generate_suite


def _state(tmp_path: Path, *, history: bool = True) -> tuple[Path, str]:
    fixtures = tmp_path / "fixtures"
    generate_suite(fixtures, long_run_minutes=1)
    root = tmp_path / "state"
    library = root / "library"
    result = import_midi(fixtures / "single-note.mid", library)
    asset_id = f"sha256:{result.asset_id}"

    update_metadata(
        library,
        asset_id,
        {
            "title": "Backup Waltz",
            "composer": "Test Composer",
            "genres": ["classical", "test"],
            "favorite": True,
            "quality_grade": "A",
        },
    )
    sidecar = Path(result.metadata_path)
    document = json.loads(sidecar.read_text(encoding="utf-8"))
    document["ai_enrichment"] = [
        {
            "provider": "test-model",
            "observed_at": "2026-08-24T00:00:00+00:00",
            "values": {"mood": "warm"},
        }
    ]
    sidecar.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    rebuild_catalog(library)

    if history:
        play_id = queue_play(
            root / "history.db",
            asset_id=asset_id,
            composition_id="composition:test",
            track_duration_seconds=30,
            occurred_at="2026-08-24T01:00:00+00:00",
        )
        mark_started(root / "history.db", play_id, occurred_at="2026-08-24T01:00:01+00:00")
        mark_completed(
            root / "history.db",
            play_id,
            occurred_at="2026-08-24T01:00:31+00:00",
            played_seconds=30,
        )
    return root, asset_id


def _zip_data(path: Path) -> dict[str, tuple[zipfile.ZipInfo, bytes]]:
    with zipfile.ZipFile(path, "r") as archive:
        return {info.filename: (info, archive.read(info)) for info in archive.infolist()}


def _write_zip(path: Path, entries: dict[str, tuple[zipfile.ZipInfo, bytes]]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, (info, payload) in entries.items():
            archive.writestr(info, payload)


def _replace_member(source: Path, destination: Path, member: str, payload: bytes) -> None:
    entries = _zip_data(source)
    info, _ = entries[member]
    entries[member] = (info, payload)
    _write_zip(destination, entries)


def _replace_member_and_manifest(
    source: Path,
    destination: Path,
    member: str,
    payload: bytes,
) -> None:
    entries = _zip_data(source)
    info, _ = entries[member]
    entries[member] = (info, payload)
    manifest_info, manifest_payload = entries["manifest.json"]
    manifest = json.loads(manifest_payload)
    record = next(item for item in manifest["files"] if item["path"] == member)
    record["size"] = len(payload)
    record["sha256"] = hashlib.sha256(payload).hexdigest()
    entries["manifest.json"] = (
        manifest_info,
        (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode(),
    )
    _write_zip(destination, entries)


def _one_member(archive: Path, suffix: str) -> str:
    with zipfile.ZipFile(archive, "r") as zipped:
        matches = [
            name
            for name in zipped.namelist()
            if name.startswith("library/assets/") and name.endswith(suffix)
        ]
    assert len(matches) == 1
    return matches[0]


def test_round_trip_preserves_durable_state_and_rebuilds_catalog(tmp_path: Path) -> None:
    root, asset_id = _state(tmp_path)
    original_sidecar = next((root / "library" / "assets").glob("*.json")).read_bytes()
    original_midi = next((root / "library" / "assets").glob("*.mid")).read_bytes()
    original_history = history_summaries(root / "history.db")
    archive = tmp_path / "backup.oo-backup.zip"

    backup = create_backup(root, archive)

    assert backup.asset_count == 1
    assert backup.file_count == 3
    assert backup.history_included is True
    assert backup.bytes_archived > 0
    with zipfile.ZipFile(archive, "r") as zipped:
        names = set(zipped.namelist())
        assert "manifest.json" in names
        assert "history.db" in names
        assert not any(name.endswith("catalog.db") for name in names)
        assert not any("secret" in name.casefold() for name in names)

    restored = tmp_path / "restored"
    report = restore_backup(archive, restored)

    assert report.asset_count == 1
    assert report.history_restored is True
    assert next((restored / "library" / "assets").glob("*.mid")).read_bytes() == original_midi
    assert next((restored / "library" / "assets").glob("*.json")).read_bytes() == original_sidecar
    assert (restored / "library" / "catalog.db").is_file()
    assert catalog_stats(restored / "library" / "catalog.db")["assets"] == 1
    indexed = get_asset(restored / "library" / "catalog.db", asset_id)
    assert indexed is not None
    assert indexed["title"] == "Backup Waltz"
    assert indexed["favorite"] is True
    assert history_summaries(restored / "history.db") == original_history
    document = json.loads(next((restored / "library" / "assets").glob("*.json")).read_text())
    assert document["ai_enrichment"][0]["values"]["mood"] == "warm"
    assert document["provenance"]["rights_status"] == "personal"


def test_backup_without_history_is_valid_and_restore_has_no_history(tmp_path: Path) -> None:
    root, _ = _state(tmp_path, history=False)
    archive = tmp_path / "backup.zip"

    report = create_backup(root, archive)
    restored = tmp_path / "restored"
    result = restore_backup(archive, restored)

    assert report.history_included is False
    assert result.history_restored is False
    assert not (restored / "history.db").exists()
    assert (restored / "library" / "catalog.db").is_file()


def test_metadata_lock_files_are_not_archived(tmp_path: Path) -> None:
    root, _ = _state(tmp_path, history=False)
    sidecar = next((root / "library" / "assets").glob("*.json"))
    sidecar.with_name(sidecar.name + ".lock").touch()
    archive = tmp_path / "backup.zip"

    create_backup(root, archive)

    with zipfile.ZipFile(archive, "r") as zipped:
        assert not any(name.endswith(".lock") for name in zipped.namelist())


@pytest.mark.parametrize("remove_suffix", [".json", ".mid"])
def test_backup_refuses_orphan_asset_pairs(tmp_path: Path, remove_suffix: str) -> None:
    root, _ = _state(tmp_path, history=False)
    next((root / "library" / "assets").glob(f"*{remove_suffix}")).unlink()

    with pytest.raises(BackupError, match="no sidecar|no MIDI object"):
        create_backup(root, tmp_path / "backup.zip")


def test_backup_refuses_corrupt_content_address_and_preserves_prior_archive(tmp_path: Path) -> None:
    root, _ = _state(tmp_path, history=False)
    midi = next((root / "library" / "assets").glob("*.mid"))
    midi.write_bytes(midi.read_bytes() + b"corruption")
    destination = tmp_path / "backup.zip"
    destination.write_bytes(b"previous-good-archive-placeholder")

    with pytest.raises(BackupError, match="library is corrupt"):
        create_backup(root, destination)

    assert destination.read_bytes() == b"previous-good-archive-placeholder"


def test_backup_refuses_unexpected_asset_file(tmp_path: Path) -> None:
    root, _ = _state(tmp_path, history=False)
    (root / "library" / "assets" / "notes.txt").write_text("not durable asset data")

    with pytest.raises(BackupError, match="unexpected file"):
        create_backup(root, tmp_path / "backup.zip")


def test_history_uses_sqlite_snapshot_and_excludes_uncommitted_writer_state(tmp_path: Path) -> None:
    root, _ = _state(tmp_path)
    history = root / "history.db"
    writer = sqlite3.connect(history)
    try:
        writer.execute("PRAGMA journal_mode = WAL")
        writer.execute("BEGIN IMMEDIATE")
        writer.execute(
            "INSERT INTO play_attempts(play_id, asset_id, queued_at) VALUES (?, ?, ?)",
            ("uncommitted", "sha256:" + "f" * 64, "2026-08-24T02:00:00+00:00"),
        )

        archive = tmp_path / "backup.zip"
        create_backup(root, archive)
    finally:
        writer.rollback()
        writer.close()

    restored = tmp_path / "restored"
    restore_backup(archive, restored)
    with sqlite3.connect(restored / "history.db") as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM play_attempts WHERE play_id='uncommitted'"
        ).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM play_attempts").fetchone()[0] == 1


def test_restore_refuses_payload_tampering_before_publication(tmp_path: Path) -> None:
    root, _ = _state(tmp_path)
    good = tmp_path / "good.zip"
    create_backup(root, good)
    midi_member = _one_member(good, ".mid")
    entries = _zip_data(good)
    _, payload = entries[midi_member]
    tampered = bytes([payload[0] ^ 0x01]) + payload[1:]
    bad = tmp_path / "tampered.zip"
    _replace_member(good, bad, midi_member, tampered)
    target = tmp_path / "restore"
    target.mkdir()

    with pytest.raises(BackupError, match="SHA-256 verification"):
        restore_backup(bad, target)

    assert target.is_dir()
    assert list(target.iterdir()) == []


def test_restore_refuses_content_address_mismatch_even_when_manifest_matches(tmp_path: Path) -> None:
    root, _ = _state(tmp_path, history=False)
    good = tmp_path / "good.zip"
    create_backup(root, good)
    sidecar_member = _one_member(good, ".json")
    entries = _zip_data(good)
    document = json.loads(entries[sidecar_member][1])
    document["asset_id"] = "sha256:" + "0" * 64
    payload = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode()
    bad = tmp_path / "bad-identity.zip"
    _replace_member_and_manifest(good, bad, sidecar_member, payload)

    with pytest.raises(BackupError, match="asset_id does not match"):
        restore_backup(bad, tmp_path / "restore")

    assert not (tmp_path / "restore").exists()


def test_restore_refuses_corrupt_history_even_when_manifest_matches(tmp_path: Path) -> None:
    root, _ = _state(tmp_path)
    good = tmp_path / "good.zip"
    create_backup(root, good)
    bad = tmp_path / "bad-history.zip"
    _replace_member_and_manifest(good, bad, "history.db", b"not a sqlite database")

    with pytest.raises(BackupError, match="history"):
        restore_backup(bad, tmp_path / "restore")

    assert not (tmp_path / "restore").exists()


@pytest.mark.parametrize("name", ["../escape", "/absolute", "library/../escape", "library\\escape"])
def test_restore_refuses_unsafe_archive_paths(tmp_path: Path, name: str) -> None:
    root, _ = _state(tmp_path, history=False)
    archive = tmp_path / "bad-path.zip"
    create_backup(root, archive)
    with zipfile.ZipFile(archive, "a") as zipped:
        zipped.writestr(name, b"evil")

    with pytest.raises(BackupError, match="unsafe|unexpected|non-canonical"):
        restore_backup(archive, tmp_path / "restore")


def test_restore_refuses_duplicate_members(tmp_path: Path) -> None:
    root, _ = _state(tmp_path, history=False)
    archive = tmp_path / "duplicate.zip"
    create_backup(root, archive)
    member = _one_member(archive, ".mid")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(archive, "a") as zipped:
            zipped.writestr(member, b"duplicate")

    with pytest.raises(BackupError, match="duplicate member"):
        restore_backup(archive, tmp_path / "restore")


def test_restore_refuses_symlink_members(tmp_path: Path) -> None:
    root, _ = _state(tmp_path, history=False)
    archive = tmp_path / "symlink.zip"
    create_backup(root, archive)
    link = zipfile.ZipInfo("evil-link")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive, "a") as zipped:
        zipped.writestr(link, b"/etc/passwd")

    with pytest.raises(BackupError, match="non-regular"):
        restore_backup(archive, tmp_path / "restore")


def test_restore_refuses_unexpected_top_level_file(tmp_path: Path) -> None:
    root, _ = _state(tmp_path, history=False)
    archive = tmp_path / "unexpected.zip"
    create_backup(root, archive)
    with zipfile.ZipFile(archive, "a") as zipped:
        zipped.writestr("openorchestrion.secrets.env", b"OPENAI_API_KEY=nope")

    with pytest.raises(BackupError, match="members do not match manifest"):
        restore_backup(archive, tmp_path / "restore")


def test_restore_refuses_unsupported_manifest_version(tmp_path: Path) -> None:
    root, _ = _state(tmp_path, history=False)
    good = tmp_path / "good.zip"
    create_backup(root, good)
    entries = _zip_data(good)
    info, payload = entries["manifest.json"]
    manifest = json.loads(payload)
    manifest["version"] = 999
    entries["manifest.json"] = (
        info,
        (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode(),
    )
    bad = tmp_path / "future.zip"
    _write_zip(bad, entries)

    with pytest.raises(BackupError, match="unsupported backup version"):
        restore_backup(bad, tmp_path / "restore")


def test_restore_refuses_duplicate_manifest_paths(tmp_path: Path) -> None:
    root, _ = _state(tmp_path, history=False)
    good = tmp_path / "good.zip"
    create_backup(root, good)
    entries = _zip_data(good)
    info, payload = entries["manifest.json"]
    manifest = json.loads(payload)
    manifest["files"].append(dict(manifest["files"][0]))
    entries["manifest.json"] = (
        info,
        (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode(),
    )
    bad = tmp_path / "duplicate-manifest.zip"
    _write_zip(bad, entries)

    with pytest.raises(BackupError, match="duplicate path"):
        restore_backup(bad, tmp_path / "restore")


def test_restore_refuses_nonempty_target(tmp_path: Path) -> None:
    root, _ = _state(tmp_path, history=False)
    archive = tmp_path / "backup.zip"
    create_backup(root, archive)
    target = tmp_path / "restore"
    target.mkdir()
    (target / "keep-me").write_text("existing state")

    with pytest.raises(BackupError, match="absent or empty"):
        restore_backup(archive, target)

    assert (target / "keep-me").read_text() == "existing state"


def test_restore_refuses_archive_symlink(tmp_path: Path) -> None:
    root, _ = _state(tmp_path, history=False)
    archive = tmp_path / "backup.zip"
    create_backup(root, archive)
    link = tmp_path / "backup-link.zip"
    link.symlink_to(archive)

    with pytest.raises(BackupError, match="regular file"):
        restore_backup(link, tmp_path / "restore")


def test_restore_refuses_symlink_target(tmp_path: Path) -> None:
    root, _ = _state(tmp_path, history=False)
    archive = tmp_path / "backup.zip"
    create_backup(root, archive)
    real = tmp_path / "real-target"
    real.mkdir()
    link = tmp_path / "restore-link"
    link.symlink_to(real, target_is_directory=True)

    with pytest.raises(BackupError, match="absent or empty"):
        restore_backup(archive, link)

    assert list(real.iterdir()) == []
