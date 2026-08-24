"""Turning a downloaded file into a reviewable candidate.

Curation research and file retrieval do not always happen in the same place. The
person who can read a license page may be unable to commit, and the machine that
can commit may have no route to the archive at all. Staging is the seam, and its
whole value is what it refuses: a file from an archive nobody agreed to use, a
file that is not the one whose licence was read, an HTML error page with a
``.mid`` name, or a claim its evidence cannot support.

None of these tests need a network. That is the design — the checks are pure
functions of a file and a claim, and the one step that genuinely needs the
internet stays in the CI job.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from openorchestrion.library.acquire import (
    ALLOWED_SOURCE_HOSTS,
    CandidateError,
    check_source_host,
    stage_candidate,
)
from openorchestrion.library.rights import RightsEvidence
from openorchestrion.testing.midi_fixtures import generate_suite

CLEARED = RightsEvidence(
    rights_status="verified-open",
    source_reference="https://commons.wikimedia.org/wiki/File:Example.mid",
    source_label="Wikimedia Commons",
    license="CC0-1.0",
    composition_rights="public-domain",
    composition_rights_basis="Composer died 1917; published 1909",
    redistribution="permitted",
)

GOOD_URL = "https://upload.wikimedia.org/wikipedia/commons/a/ab/Example.mid"


@pytest.fixture
def download(tmp_path: Path) -> Path:
    """A file standing in for something a runner just fetched."""
    source = tmp_path / "fixtures"
    generate_suite(source, long_run_minutes=1)
    target = tmp_path / "download.mid"
    target.write_bytes((source / "two-piano-split.mid").read_bytes())
    return target


def digest_of(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(manifest: Path) -> list[dict[str, str]]:
    with manifest.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


# ------------------------------------------------------------- source policy


@pytest.mark.parametrize("host", sorted(ALLOWED_SOURCE_HOSTS))
def test_the_archives_we_agreed_to_work_through_are_allowed(host: str) -> None:
    check_source_host(f"https://{host}/some/file.mid")


def test_an_unagreed_host_is_refused_and_says_what_is_allowed() -> None:
    """Otherwise this is a job that pulls any URL on the internet into the repo."""
    with pytest.raises(CandidateError) as caught:
        check_source_host("https://midi-archive.example.net/free/whatever.mid")
    assert "not an allowed source" in str(caught.value)
    assert "commons.wikimedia.org" in str(caught.value)


def test_a_lookalike_host_does_not_pass() -> None:
    """Substring matching would accept commons.wikimedia.org.attacker.test."""
    with pytest.raises(CandidateError):
        check_source_host("https://commons.wikimedia.org.attacker.test/x.mid")


def test_a_url_without_a_host_is_refused() -> None:
    with pytest.raises(CandidateError, match="no host"):
        check_source_host("file:///etc/passwd")


def test_host_matching_ignores_case() -> None:
    check_source_host("https://Commons.WikiMedia.ORG/wiki/File:X.mid")


# --------------------------------------------------------------- the digest


def test_a_file_matching_its_researched_digest_is_staged(
    tmp_path: Path, download: Path
) -> None:
    staged = stage_candidate(
        download,
        tmp_path / "candidates",
        CLEARED,
        filename="example.mid",
        expected_sha256=digest_of(download),
        source_url=GOOD_URL,
    )
    assert staged.digest_was_verified is True
    assert staged.note_count > 0
    assert (tmp_path / "candidates" / "example.mid").is_file()


def test_a_digest_mismatch_is_refused_as_a_rights_problem(
    tmp_path: Path, download: Path
) -> None:
    with pytest.raises(CandidateError) as caught:
        stage_candidate(
            download,
            tmp_path / "candidates",
            CLEARED,
            expected_sha256="0" * 64,
            source_url=GOOD_URL,
        )
    assert "evidence was gathered about a different file" in str(caught.value)
    assert not (tmp_path / "candidates").exists()


def test_an_observed_digest_is_reported_as_weaker_than_a_verified_one(
    tmp_path: Path, download: Path
) -> None:
    """'I checked this file's terms' and 'this is a file' must not look alike.

    Omitting the digest is allowed because not every source publishes one, but a
    reviewer has to be told which of the two claims they are being asked to
    approve.
    """
    staged = stage_candidate(
        download, tmp_path / "candidates", CLEARED, source_url=GOOD_URL
    )
    assert staged.digest_was_verified is False
    assert staged.sha256 == digest_of(download)


# ------------------------------------------------------------- is it music


def test_an_html_error_page_with_a_midi_name_is_refused(tmp_path: Path) -> None:
    """What archives actually serve when a link has rotted."""
    page = tmp_path / "download.mid"
    page.write_bytes(b"<!DOCTYPE html><html><body>404 Not Found</body></html>")

    with pytest.raises(CandidateError, match="not a readable MIDI file"):
        stage_candidate(page, tmp_path / "candidates", CLEARED, source_url=GOOD_URL)


def test_an_empty_download_is_refused(tmp_path: Path) -> None:
    empty = tmp_path / "download.mid"
    empty.write_bytes(b"")
    with pytest.raises(CandidateError, match="download produced nothing"):
        stage_candidate(empty, tmp_path / "candidates", CLEARED, source_url=GOOD_URL)


def test_a_midi_file_with_no_notes_is_refused(tmp_path: Path) -> None:
    """Structurally valid and musically empty is still not repertoire."""
    from mido import MidiFile, MidiTrack

    silent = MidiFile(type=1, ticks_per_beat=480)
    silent.tracks.append(MidiTrack())
    silent.save(tmp_path / "download.mid")

    with pytest.raises(CandidateError, match="no notes"):
        stage_candidate(
            tmp_path / "download.mid", tmp_path / "candidates", CLEARED, source_url=GOOD_URL
        )


def test_an_oversized_download_is_refused(tmp_path: Path, download: Path) -> None:
    with pytest.raises(CandidateError, match="above the"):
        stage_candidate(
            download, tmp_path / "candidates", CLEARED, source_url=GOOD_URL, max_bytes=8
        )


# ------------------------------------------------------------- the evidence


def test_a_claim_its_evidence_cannot_support_is_refused(
    tmp_path: Path, download: Path
) -> None:
    from dataclasses import replace

    with pytest.raises(CandidateError, match="not supported by the recorded evidence"):
        stage_candidate(
            download,
            tmp_path / "candidates",
            replace(CLEARED, license="Free for personal use"),
            source_url=GOOD_URL,
        )
    assert not (tmp_path / "candidates").exists()


def test_nothing_is_written_when_any_check_fails(tmp_path: Path, download: Path) -> None:
    """A refused candidate must not leave a half-staged directory behind."""
    with pytest.raises(CandidateError):
        stage_candidate(
            download, tmp_path / "candidates", CLEARED, expected_sha256="0" * 64
        )
    assert not (tmp_path / "candidates").exists()


# -------------------------------------------------------------- the manifest


def test_the_manifest_records_the_whole_evidence_row(
    tmp_path: Path, download: Path
) -> None:
    stage_candidate(
        download,
        tmp_path / "candidates",
        CLEARED,
        filename="example.mid",
        expected_sha256=digest_of(download),
        source_url=GOOD_URL,
    )
    row = rows(tmp_path / "candidates" / "catalog.csv")[0]

    assert row["path"] == "example.mid"
    assert row["sha256"] == digest_of(download)
    assert row["license"] == "CC0-1.0"
    assert row["composition_rights_basis"] == CLEARED.composition_rights_basis


def test_a_second_candidate_joins_the_same_manifest(
    tmp_path: Path, download: Path
) -> None:
    for name in ("first.mid", "second.mid"):
        stage_candidate(
            download, tmp_path / "candidates", CLEARED, filename=name, source_url=GOOD_URL
        )
    assert [row["path"] for row in rows(tmp_path / "candidates" / "catalog.csv")] == [
        "first.mid",
        "second.mid",
    ]


def test_restaging_replaces_a_row_rather_than_duplicating_it(
    tmp_path: Path, download: Path
) -> None:
    """Correcting evidence must not leave two rows disagreeing about one file.

    The audit would then depend on whichever a reader happened to see first.
    """
    from dataclasses import replace

    stage_candidate(
        download, tmp_path / "candidates", CLEARED, filename="x.mid", source_url=GOOD_URL
    )
    stage_candidate(
        download,
        tmp_path / "candidates",
        replace(CLEARED, source_label="Corrected Archive"),
        filename="x.mid",
        source_url=GOOD_URL,
    )

    stored = rows(tmp_path / "candidates" / "catalog.csv")
    assert len(stored) == 1
    assert stored[0]["source_label"] == "Corrected Archive"


def test_the_staged_directory_passes_the_repository_contract(
    tmp_path: Path, download: Path
) -> None:
    """The end the workflow is for: what it stages must already be shippable."""
    from openorchestrion.library.policy import audit_committed_music

    stage_candidate(
        download,
        tmp_path / "candidates",
        CLEARED,
        filename="example.mid",
        expected_sha256=digest_of(download),
        source_url=GOOD_URL,
    )
    assert audit_committed_music(tmp_path / "candidates") == []


def test_a_staged_candidate_imports_with_its_evidence_intact(
    tmp_path: Path, download: Path
) -> None:
    """Staging feeds the ordinary manifest import, not a parallel path."""
    import json

    from openorchestrion.library.importer import import_manifest, read_curation_manifest

    staged_dir = tmp_path / "candidates"
    stage_candidate(
        download,
        staged_dir,
        CLEARED,
        filename="example.mid",
        expected_sha256=digest_of(download),
        source_url=GOOD_URL,
    )

    report = import_manifest(
        read_curation_manifest(staged_dir / "catalog.csv"),
        tmp_path / "library",
        base_dir=staged_dir,
    )
    assert not report.failed

    provenance = json.loads(Path(report.imported[0].metadata_path).read_text())["provenance"]
    assert provenance["rights_status"] == "verified-open"
    assert provenance["license"] == "CC0-1.0"
