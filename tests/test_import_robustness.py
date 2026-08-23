"""Ingestion must survive a real-world MIDI collection.

Public archives are full of truncated downloads, empty placeholders and files
whose extension lies about their contents. Before this, one such file aborted
the whole run and — because discovery is sorted — everything after it was
silently never imported.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from openorchestrion.library.importer import (
    DEFAULT_MAX_BYTES,
    ImportReport,
    import_paths,
)
from openorchestrion.testing.midi_fixtures import single_note

# A header that declares one track, then stops before the track data arrives.
TRUNCATED = b"MThd\x00\x00\x00\x06\x00\x01\x00\x01\x01\xe0MTrk\x00\x00\x00\x03\xff\x2f"


@pytest.fixture
def collection(tmp_path: Path) -> Path:
    """A directory shaped like a real download: some good files, some junk.

    Names are chosen so the bad files sort *before* good ones — the original
    failure silently dropped everything alphabetically after the first error.
    """
    source = tmp_path / "collection"
    source.mkdir()
    single_note().save(source / "c-good.mid")
    single_note().save(source / "z-good.mid")
    (source / "a-truncated.mid").write_bytes(TRUNCATED)
    (source / "b-empty.mid").write_bytes(b"")
    (source / "d-not-midi.mid").write_bytes(b"<!DOCTYPE html><html>404 Not Found</html>")
    return source


def test_one_bad_file_does_not_lose_the_rest(collection: Path, tmp_path: Path) -> None:
    report = import_paths([collection], tmp_path / "lib")
    assert len(report.imported) == 2
    assert len(report.failed) == 3
    # The two good files are byte-identical, so content addressing stores one.
    assert len({result.asset_id for result in report.imported}) == 1


def test_failures_say_which_file_and_why(collection: Path, tmp_path: Path) -> None:
    report = import_paths([collection], tmp_path / "lib")
    by_name = {Path(failure.source).name: failure for failure in report.failed}
    assert set(by_name) == {"a-truncated.mid", "b-empty.mid", "d-not-midi.mid"}
    assert by_name["b-empty.mid"].reason == "file is empty"
    # EOFError carries no message; repeating the class name would tell the
    # user nothing about their file.
    truncated = by_name["a-truncated.mid"]
    assert truncated.error_type == "EOFError"
    assert "truncated" in truncated.reason
    for failure in report.failed:
        assert failure.error_type
        assert failure.reason


def test_good_files_are_actually_stored(collection: Path, tmp_path: Path) -> None:
    library = tmp_path / "lib"
    import_paths([collection], library)
    stored = list((library / "assets").glob("*.mid"))
    assert stored, "nothing was written"
    for midi in stored:
        assert midi.with_suffix(".json").is_file(), "sidecar missing for a stored asset"


def test_fail_fast_stops_at_the_first_bad_file(collection: Path, tmp_path: Path) -> None:
    report = import_paths([collection], tmp_path / "lib", fail_fast=True)
    assert len(report.failed) == 1
    assert Path(report.failed[0].source).name == "a-truncated.mid"
    assert report.imported == ()


def test_oversized_files_are_skipped_not_parsed(tmp_path: Path) -> None:
    source = tmp_path / "big"
    source.mkdir()
    single_note().save(source / "ok.mid")
    (source / "huge.mid").write_bytes(b"MThd" + b"\x00" * 4096)

    report = import_paths([source], tmp_path / "lib", max_bytes=1024)
    assert len(report.imported) == 1
    assert len(report.failed) == 1
    assert "import limit" in report.failed[0].reason


def test_default_size_limit_admits_ordinary_music(tmp_path: Path) -> None:
    """The ceiling must not reject real repertoire; SMFs are tiny."""
    source = tmp_path / "normal"
    source.mkdir()
    single_note().save(source / "ok.mid")
    assert (source / "ok.mid").stat().st_size < DEFAULT_MAX_BYTES
    assert not import_paths([source], tmp_path / "lib").failed


def test_a_clean_collection_reports_no_failures(tmp_path: Path) -> None:
    source = tmp_path / "clean"
    source.mkdir()
    single_note().save(source / "one.mid")
    report = import_paths([source], tmp_path / "lib")
    assert isinstance(report, ImportReport)
    assert report.failed == ()
    assert len(report.created) == 1


def test_reimport_is_idempotent_and_not_reported_as_created(tmp_path: Path) -> None:
    source = tmp_path / "clean"
    source.mkdir()
    single_note().save(source / "one.mid")
    library = tmp_path / "lib"

    assert len(import_paths([source], library).created) == 1
    second = import_paths([source], library)
    assert second.failed == ()
    assert second.created == ()
    assert len(second.imported) == 1


def test_report_counts_round_trip_to_json(collection: Path, tmp_path: Path) -> None:
    payload = import_paths([collection], tmp_path / "lib").to_dict()
    assert payload["counts"] == {
        "imported": 2,
        "created": 1,
        "already_present": 1,
        "failed": 3,
    }
    assert len(payload["failed"]) == 3


def test_explicit_missing_source_is_reported(tmp_path: Path) -> None:
    missing = tmp_path / "missing.mid"
    report = import_paths([missing], tmp_path / "lib")
    assert report.imported == ()
    assert len(report.failed) == 1
    assert report.failed[0].error_type == "FileNotFoundError"
    assert report.failed[0].source == str(missing)
    assert "does not exist" in report.failed[0].reason


def test_explicit_unsupported_file_is_reported(tmp_path: Path) -> None:
    wrong = tmp_path / "notes.txt"
    wrong.write_text("not midi", encoding="utf-8")
    report = import_paths([wrong], tmp_path / "lib")
    assert report.imported == ()
    assert len(report.failed) == 1
    assert report.failed[0].error_type == "ValueError"
    assert "unsupported MIDI extension" in report.failed[0].reason


def test_programmatic_negative_max_bytes_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="max_bytes must be non-negative"):
        import_paths([], tmp_path / "lib", max_bytes=-1)


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "openorchestrion.library.importer", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_exits_non_zero_when_any_file_failed(collection: Path, tmp_path: Path) -> None:
    """A scripted import must not look successful because most files parsed."""
    result = _run_cli(str(collection), "--library-root", str(tmp_path / "lib"))
    assert result.returncode == 1
    assert "skipped:" in result.stdout
    assert "imported:" in result.stdout


def test_cli_exits_zero_on_a_clean_collection(tmp_path: Path) -> None:
    source = tmp_path / "clean"
    source.mkdir()
    single_note().save(source / "one.mid")
    result = _run_cli(str(source), "--library-root", str(tmp_path / "lib"))
    assert result.returncode == 0
    assert "skipped:" not in result.stdout


def test_cli_missing_source_exits_non_zero(tmp_path: Path) -> None:
    missing = tmp_path / "missing.mid"
    result = _run_cli(str(missing), "--library-root", str(tmp_path / "lib"))
    assert result.returncode == 1
    assert "path does not exist" in result.stdout


def test_cli_rejects_negative_max_bytes(tmp_path: Path) -> None:
    source = tmp_path / "clean"
    source.mkdir()
    single_note().save(source / "one.mid")
    result = _run_cli(str(source), "--max-bytes", "-1")
    assert result.returncode == 2
    assert "--max-bytes must be non-negative" in result.stderr
