"""Acquisition tests exercise real MIDI qualification and publication boundaries."""

from contextlib import closing
import hashlib
import io
import json
import os
import sqlite3
import time
import zipfile
import subprocess

from mido import Message, MidiFile, MidiTrack, MetaMessage
import pytest

from openorchestrion.library import acquisition as acq
from openorchestrion.library import acquisition_publish as publication
from openorchestrion.library.acquisition_sources import SOURCES, checked_url, page_links
from openorchestrion.library.acquisition_worker import assess
from openorchestrion.library.catalog import rebuild_catalog, catalog_stats
from openorchestrion.library.quality import VERSION


def midi_bytes(melody=False, renamed=False):
    track = MidiTrack([Message("program_change", program=0)])
    if renamed:
        track.append(MetaMessage("track_name", name="Same music, different tag"))
    for i in range(144):
        notes = [60 + i % 12] if melody else [36 + i % 12, 48 + i % 12, 60 + i % 12, 72 + i % 12]
        duration = 100 + i % 12 * 11
        for j, note in enumerate(notes):
            track.append(
                Message(
                    "note_on", note=note, velocity=60 + i % 24, time=960 - duration if j == 0 else 0
                )
            )
        for j, note in enumerate(notes):
            track.append(Message("note_off", note=note, time=duration if j == 0 else 0))
    midi = MidiFile()
    midi.tracks = [track]
    output = io.BytesIO()
    midi.save(file=output)
    return output.getvalue()


@pytest.fixture
def library(tmp_path):
    root = tmp_path / "state" / "library"
    (root / "assets").mkdir(parents=True)
    (root / "listening-admission.json").write_text(
        json.dumps({"policy_version": VERSION, "asset_ids": []})
    )
    with sqlite3.connect(root / "quality.sqlite3") as conn:
        conn.execute("CREATE TABLE quality(asset_id TEXT PRIMARY KEY, record TEXT)")
    rebuild_catalog(root)
    return root


def candidate(tmp_path, raw=None):
    folder = tmp_path / "candidate"
    folder.mkdir()
    (folder / "download.mid").write_bytes(raw or midi_bytes())
    return assess(
        folder,
        {
            "label": "Test publisher",
            "title": "Complete arrangement",
            "reference": "https://example.org/music",
            "genre": "classical",
        },
    )


def test_real_arrangement_qualifies_but_expressive_melody_does_not(tmp_path):
    complete = candidate(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    incomplete = candidate(other, midi_bytes(melody=True))
    assert complete["status"] == "qualified"
    assert complete["display"]["verification"] == "structural_assessment"
    assert incomplete["status"] != "qualified"
    assert "completeness_unresolved" in incomplete["reasons"]


def test_publication_rolls_forward_after_catalog_failure(library, tmp_path, monkeypatch):
    record = candidate(tmp_path)
    journal = tmp_path / "journal.json"
    original = publication.reindex_asset
    monkeypatch.setattr(publication, "reindex_asset", lambda *args: False)
    with pytest.raises(RuntimeError, match="catalog"):
        publication.publish(library, journal, record)
    assert not json.loads(journal.read_text()).get("published")
    assert catalog_stats(library / "catalog.db")["assets"] == 0
    monkeypatch.setattr(publication, "reindex_asset", original)
    publication.publish(library, journal)
    publication.publish(library, journal)
    assert catalog_stats(library / "catalog.db")["assets"] == 1
    assert json.loads(journal.read_text())["published"]


def test_publication_rejects_unqualified_and_preserves_existing_metadata(library, tmp_path):
    record = candidate(tmp_path)
    journal = tmp_path / "journal.json"
    with pytest.raises(ValueError, match="not qualified"):
        publication.publish(library, journal, record | {"status": "unresolved"})
    publication.publish(library, journal, record)
    sidecar = library / "assets" / (record["asset_id"][7:] + ".json")
    sidecar.write_text("user edited metadata")
    with pytest.raises(ValueError, match="collision"):
        publication.publish(library, journal)
    assert sidecar.read_text() == "user edited metadata"


@pytest.mark.skipif(os.name != "posix", reason="Linux appliance lock")
def test_dead_owned_lock_recovers_but_unknown_and_live_locks_do_not(library):
    lock = library / ".curation-lock"
    lock.symlink_to("acquisition-99999999-dead-1")
    with publication.publication_lock(library):
        with pytest.raises(RuntimeError, match="running"):
            with publication.publication_lock(library):
                pass
    lock.mkdir()
    with pytest.raises(RuntimeError, match="curation lock"):
        with publication.publication_lock(library):
            pass
    assert lock.is_dir()


def test_seed_requires_checksum_and_full_archive_coverage(library, tmp_path):
    digest = "1" * 64
    archived = library / "archive" / "old" / "assets"
    archived.mkdir(parents=True)
    (archived / (digest + ".json")).write_text("{}")
    raw = json.dumps(
        {"asset_id": "sha256:" + digest, "facts": {"fingerprint": "old-playback"}}
    ).encode()
    archive = tmp_path / "facts.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("quality-facts.jsonl", raw)
    with pytest.raises(ValueError, match="checksum"):
        acq.seed(library, archive, "wrong")
    assert acq.seed(library, archive, hashlib.sha256(raw).hexdigest()) == 1
    with closing(acq.connect(library)) as conn:
        assert conn.execute("SELECT fingerprint FROM known").fetchone()[0] == "old-playback"


def test_archive_bytes_and_retagged_playback_are_not_readmitted(library, tmp_path):
    raw = midi_bytes()
    record = candidate(tmp_path, raw)
    source = next(s for s in SOURCES if s.key == "vgmusic")

    class Client:
        def __init__(self, raw):
            self.raw = raw

        def get(self, *args, **kwargs):
            return self.raw

    state = tmp_path / "acquisition"
    state.mkdir()
    item = {
        "url": "https://www.vgmusic.com/music/test.mid",
        "reference": "https://www.vgmusic.com/music/",
        "title": "Another filename",
    }
    with closing(acq.connect(library)) as conn:
        acq.known_record(conn, record | {"status": "excluded"})
        assert acq.evaluate(library, state, conn, source, item, Client(raw)) == "duplicate_bytes"
        assert (
            acq.evaluate(library, state, conn, source, item, Client(midi_bytes(renamed=True)))
            == "duplicate_playback"
        )
    assert catalog_stats(library / "catalog.db")["assets"] == 0


def test_actual_worker_admission_is_idempotent(library, tmp_path):
    source = next(s for s in SOURCES if s.key == "vgmusic")

    class Client:
        def get(self, *args, **kwargs):
            return midi_bytes()

    state = tmp_path / "acquisition"
    state.mkdir()
    item = {
        "url": "https://www.vgmusic.com/music/test.mid",
        "reference": "https://www.vgmusic.com/music/",
        "title": "Complete test",
    }
    with closing(acq.connect(library)) as conn:
        assert acq.evaluate(library, state, conn, source, item, Client()) == "admitted"
        assert acq.evaluate(library, state, conn, source, item, Client()) == "duplicate_bytes"
        assert conn.execute("SELECT count(*) FROM decisions").fetchone()[0] == 1
    assert catalog_stats(library / "catalog.db")["assets"] == 1
    assert not list((state / "staging").iterdir())


def test_worker_installation_failure_is_not_a_quality_rejection(library, tmp_path, monkeypatch):
    source = next(s for s in SOURCES if s.key == "vgmusic")

    class Client:
        def get(self, *args, **kwargs):
            return midi_bytes()

    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "python", stderr=b"No module named worker")

    monkeypatch.setattr(acq.subprocess, "run", fail)
    state = tmp_path / "acquisition"
    state.mkdir()
    item = {
        "url": "https://www.vgmusic.com/music/test.mid",
        "reference": "https://www.vgmusic.com/music/",
        "title": "Complete test",
    }
    with closing(acq.connect(library)) as conn:
        with pytest.raises(RuntimeError, match="retained for retry"):
            acq.evaluate(library, state, conn, source, item, Client())
        assert conn.execute("SELECT count(*) FROM known").fetchone()[0] == 0


def test_publisher_backing_track_label_overrides_rich_arrangement(tmp_path):
    folder = tmp_path / "candidate"
    folder.mkdir()
    (folder / "download.mid").write_bytes(midi_bytes())
    record = assess(
        folder,
        {
            "label": "Test publisher",
            "title": "Backing track",
            "reference": "https://example.org/music",
            "genre": "classical",
        },
    )
    assert record["status"] == "excluded"
    assert "confirmed_partial_arrangement" in record["reasons"]


def test_source_failures_back_off_and_other_sources_continue(library, tmp_path, monkeypatch):
    class Client:
        def __init__(self, source):
            self.source = source

        def get(self, *args, **kwargs):
            if self.source.key == "smd":
                raise OSError("offline")
            return b"<html></html>"

    monkeypatch.setattr(acq, "Client", Client)
    report = acq.run(library, tmp_path / "acquisition", only=["smd", "vgmusic"])
    assert [s["status"] for s in report["sources"]] == ["error", "ok"]
    assert acq.status(library)["status"] == "degraded"
    report = acq.run(library, tmp_path / "acquisition", only=["smd"])
    assert report["sources"][0]["status"] == "backoff"


def test_download_budget_retains_unprocessed_links(library, tmp_path, monkeypatch):
    source = next(s for s in SOURCES if s.key == "vgmusic")

    class Client:
        def __init__(self, source):
            pass

        def get(self, *args):
            return b'<a href="a.mid">A</a><a href="b.mid">B</a>'

    monkeypatch.setattr(acq, "Client", Client)
    monkeypatch.setattr(acq, "evaluate", lambda *args: "not_qualified")
    with closing(acq.connect(library)) as conn:
        first = acq.run_source(library, tmp_path, conn, source, 1, 1)
        second = acq.run_source(library, tmp_path, conn, source, 1, 1)
        assert first["counts"]["not_qualified"] == second["counts"]["not_qualified"] == 1
        assert (
            conn.execute(
                "SELECT count(*) FROM frontier WHERE json_extract(payload,'$.kind')='midi'"
            ).fetchone()[0]
            == 2
        )


def test_source_hosts_paths_and_v2_download_links():
    smd = next(s for s in SOURCES if s.key == "smd")
    good = "https://www.audiolabs-erlangen.de/content/resources/MIR/SMD/02_midi/data/midi/piece.mid"
    assert (
        page_links(smd, smd.seeds[0], ('<a href="' + good + '">mid</a>').encode())[0]["url"] == good
    )
    for url in [
        "https://evil.example/a.mid",
        "https://www.audiolabs-erlangen.de/private/a.mid",
        "https://www.audiolabs-erlangen.de/resources/MIR/SMD/%2e%2e/secret",
        "https://user:pass@www.audiolabs-erlangen.de/resources/MIR/SMD/x.mid",
    ]:
        with pytest.raises(ValueError):
            checked_url(smd, url)


def test_stale_status_and_backup_preserve_rejection_history(library, tmp_path):
    from openorchestrion.backup import create_backup, restore_backup

    with closing(acq.connect(library)) as conn:
        acq.known_record(
            conn,
            {"asset_id": "sha256:" + "3" * 64, "status": "excluded", "reasons": ["incomplete"]},
        )
        acq.save_status(
            conn, {"status": "running", "started_at": time.time() - 3600, "sources": []}
        )
    assert acq.status(library)["status"] == "interrupted"
    archive = tmp_path / "backup.zip"
    create_backup(library.parent, archive)
    restored = tmp_path / "restored"
    restore_backup(archive, restored)
    with closing(acq.connect(restored / "library")) as conn:
        assert conn.execute("SELECT verdict FROM known").fetchone()[0] == "excluded"
        assert json.loads(conn.execute("SELECT record FROM decisions").fetchone()[0])[
            "reasons"
        ] == ["incomplete"]


def test_backup_cannot_capture_ledger_mid_acquisition(library, tmp_path):
    from openorchestrion.backup import create_backup, BackupError

    with closing(acq.connect(library)):
        pass
    with publication.snapshot_lock(library):
        with pytest.raises(BackupError, match="retry later"):
            create_backup(library.parent, tmp_path / "raced.zip")
    assert not (tmp_path / "raced.zip").exists()


def test_snapshot_lock_does_not_require_write_permission(library):
    path = library / '.acquisition-snapshot.lock'
    previous = os.umask(0o077)
    try:
        with publication.snapshot_lock(library):
            assert path.stat().st_mode & 0o777 == 0o644
    finally:
        os.umask(previous)
    path.chmod(0o444)
    with publication.snapshot_lock(library):
        with pytest.raises(RuntimeError, match='retry later'):
            with publication.snapshot_lock(library):
                pass


def test_new_user_can_initialize_and_publish_without_private_seed(tmp_path):
    root = tmp_path / "new-library"
    acq.initialize_empty(root)
    record = candidate(tmp_path)
    assert record["status"] == "qualified"
    publication.publish(root, tmp_path / "publication.json", record)
    assert catalog_stats(root / "catalog.db")["assets"] == 1
    with pytest.raises(ValueError, match="existing collection"):
        acq.initialize_empty(root)
    assert catalog_stats(root / "catalog.db")["assets"] == 1


def test_empty_bootstrap_preserves_rejection_history_and_refuses_unindexed_files(tmp_path):
    root = tmp_path / "library"
    acq.initialize_empty(root)
    with closing(acq.connect(root)) as conn, conn:
        conn.execute("INSERT INTO known VALUES (?,?,?,?)", ("sha256:discarded", "fp", "source", "rejected"))
    acq.initialize_empty(root)
    with closing(acq.connect(root)) as conn:
        assert conn.execute("SELECT verdict FROM known").fetchone()[0] == "rejected"
    (root / "assets" / "unindexed.mid").write_bytes(b"do not erase")
    with pytest.raises(ValueError, match="existing collection"):
        acq.initialize_empty(root)
