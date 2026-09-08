import hashlib
import io
import stat
import zipfile

import mido
import pytest

from openorchestrion.library.acquire import CandidateError, stage_bundle_member
from openorchestrion.library.bundle import inspect_bundle
from openorchestrion.testing.midi_fixtures import SUITE_RIGHTS


def midi_bytes():
    midi = mido.MidiFile()
    midi.tracks.append(mido.MidiTrack([
        mido.Message("note_on", note=60, velocity=70),
        mido.Message("note_off", note=60, time=480),
    ]))
    stream = io.BytesIO()
    midi.save(file=stream)
    return stream.getvalue()


def bundle(tmp_path, entries):
    path = tmp_path / "music.zip"
    with zipfile.ZipFile(path, "w") as archive:
        for name, raw in entries:
            archive.writestr(name, raw)
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def test_audit_accounts_for_every_member_without_extracting_or_admitting(tmp_path):
    path, digest = bundle(tmp_path, [("score/full.mid", midi_bytes()),
                                    ("part.mid", b"HTML error"), ("LICENSE", b"terms")])
    report = inspect_bundle(path, expected_sha256=digest)
    assert [row["status"] for row in report["members"]] == [
        "readable-midi", "invalid-midi", "not-midi"]
    assert report["admitted"] is False
    assert not (tmp_path / "score").exists()


@pytest.mark.parametrize("name", ["../escape.mid", "/absolute.mid", "x\\escape.mid", "C:evil.mid"])
def test_archive_paths_cannot_escape(tmp_path, name):
    path, digest = bundle(tmp_path, [(name, midi_bytes())])
    with pytest.raises(ValueError, match="unsafe"):
        inspect_bundle(path, expected_sha256=digest)


def test_archive_refuses_symlinks_duplicates_and_oversize(tmp_path, monkeypatch):
    link = zipfile.ZipInfo("link.mid")
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    path, digest = bundle(tmp_path, [(link, b"target")])
    with pytest.raises(ValueError, match="non-regular"):
        inspect_bundle(path, expected_sha256=digest)
    path, digest = bundle(tmp_path, [("A.mid", midi_bytes()), ("a.mid", midi_bytes())])
    with pytest.raises(ValueError, match="duplicate"):
        inspect_bundle(path, expected_sha256=digest)
    monkeypatch.setattr("openorchestrion.library.bundle.MAX_MEMBER_BYTES", 10)
    path, digest = bundle(tmp_path, [("a.mid", midi_bytes())])
    with pytest.raises(ValueError, match="size limits"):
        inspect_bundle(path, expected_sha256=digest)


def test_staging_requires_exact_archive_and_member_and_preserves_full_audit(tmp_path):
    raw = midi_bytes()
    path, digest = bundle(tmp_path, [("score/full.mid", raw), ("README", b"fixture")])
    destination = tmp_path / "candidates"
    options = dict(member="score/full.mid", archive_sha256=digest,
                   expected_sha256=hashlib.sha256(raw).hexdigest(), filename="full.mid")
    with pytest.raises(CandidateError, match="archive digest"):
        stage_bundle_member(path, destination, SUITE_RIGHTS,
                            **{**options, "archive_sha256": "0" * 64})
    with pytest.raises(CandidateError, match="member digest"):
        stage_bundle_member(path, destination, SUITE_RIGHTS,
                            **{**options, "expected_sha256": "0" * 64})
    assert not destination.exists()
    staged = stage_bundle_member(path, destination, SUITE_RIGHTS, **options)
    assert staged.digest_was_verified
    assert (destination / "full.mid").read_bytes() == raw
    assert (destination / f"bundle-{digest}.json").exists()
    assert not (destination / "README").exists()


def test_invalid_sibling_blocks_staging(tmp_path):
    raw = midi_bytes()
    path, digest = bundle(tmp_path, [("full.mid", raw), ("bad.mid", b"bad")])
    with pytest.raises(CandidateError, match="invalid or empty"):
        stage_bundle_member(path, tmp_path / "out", SUITE_RIGHTS,
                            member="full.mid", archive_sha256=digest,
                            expected_sha256=hashlib.sha256(raw).hexdigest(), filename="full.mid")
    assert not (tmp_path / "out").exists()
