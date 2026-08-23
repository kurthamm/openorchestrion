"""What this repository is allowed to distribute.

The rule is that no MIDI is published without established redistribution
rights. The enforcement used to scan ``music/`` alone, which quietly assumed
committed MIDI only ever lands in one directory. It does not: a rejected
curation candidate parked in a research directory is published the moment it is
pushed, and the audit would have waved it past.

Scoping to what Git tracks fixes both halves of that. It covers the whole
repository, and it stops caring about files the repository does not carry — the
conformance suite a developer generates into an ignored directory is theirs, not
ours.
"""

from __future__ import annotations

import csv
import hashlib
import subprocess
from pathlib import Path

import pytest

from openorchestrion.library.policy import (
    NotATrackedTreeError,
    audit_music_files,
    audit_tracked_music,
    count_tracked_music,
    tracked_midi_files,
)
from openorchestrion.testing.midi_fixtures import generate_suite

CLEARED = {
    "rights_status": "verified-open",
    "source_reference": "https://example.org/scores/rag.mid",
    "license": "CC0-1.0",
    "composition_rights": "public-domain",
    "composition_rights_basis": "Composer died 1917; published 1899",
    "redistribution": "permitted",
}
COLUMNS = ("path", "sha256", *CLEARED)


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def fixtures(tmp_path: Path) -> Path:
    source = tmp_path / "fixtures"
    generate_suite(source, long_run_minutes=1)
    return source


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    return root


def add_midi(repo: Path, fixtures: Path, relative: str, *, track: bool = True) -> Path:
    target = repo / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((fixtures / "single-note.mid").read_bytes())
    if track:
        git(repo, "add", "--", relative)
    return target


def add_manifest(directory: Path, names: list[str], **overrides: str) -> Path:
    manifest = directory / "catalog.csv"
    with manifest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        for name in names:
            digest = hashlib.sha256((directory / name).read_bytes()).hexdigest()
            writer.writerow({"path": name, "sha256": digest, **CLEARED, **overrides})
    return manifest


# ----------------------------------------------------------- what Git carries


def test_tracked_music_without_evidence_is_refused(repo: Path, fixtures: Path) -> None:
    add_midi(repo, fixtures, "music/starter/smuggled.mid")
    offenders = audit_tracked_music(repo)
    assert len(offenders) == 1
    assert "smuggled.mid" in offenders[0]


def test_the_check_covers_the_whole_repository_not_just_music(
    repo: Path, fixtures: Path
) -> None:
    """The gap this change closes.

    A rejected candidate parked in a research directory is published the moment
    it is pushed. Scanning ``music/`` alone waved exactly that case through.
    """
    add_midi(repo, fixtures, "curation/candidates/rejected.mid")
    offenders = audit_tracked_music(repo)
    assert len(offenders) == 1
    assert "curation/candidates/rejected.mid" in offenders[0]


def test_an_untracked_file_is_not_this_check_s_business(repo: Path, fixtures: Path) -> None:
    """Someone's working copy is theirs. The repository publishes nothing here."""
    add_midi(repo, fixtures, "downloads/whatever.mid", track=False)
    assert audit_tracked_music(repo) == []


def test_generated_fixtures_in_an_ignored_directory_do_not_fail_the_check(
    repo: Path, fixtures: Path
) -> None:
    """A filesystem walk would fail for a developer and nobody else.

    The documented way to work with the conformance suite is to generate it into
    ``build/``, which is ignored. Those files are not published, so they are not
    this rule's concern, and a check that punished them would be wrong on the
    one machine where it fired.
    """
    (repo / ".gitignore").write_text("build/\n", encoding="utf-8")
    git(repo, "add", ".gitignore")
    generate_suite(repo / "build" / "midi-fixtures", long_run_minutes=1)

    assert audit_tracked_music(repo) == []
    assert count_tracked_music(repo) == 0


def test_a_tracked_file_missing_from_the_working_tree_is_skipped(
    repo: Path, fixtures: Path
) -> None:
    """Tracked but absent is a different problem, and not this check's to report."""
    target = add_midi(repo, fixtures, "music/starter/gone.mid")
    target.unlink()
    assert audit_tracked_music(repo) == []


# ------------------------------------------------------------ with evidence


def test_a_tracked_file_its_manifest_vouches_for_passes(repo: Path, fixtures: Path) -> None:
    starter = repo / "music" / "starter"
    add_midi(repo, fixtures, "music/starter/cleared.mid")
    add_manifest(starter, ["cleared.mid"])
    git(repo, "add", "music/starter/catalog.csv")

    assert audit_tracked_music(repo) == []
    assert count_tracked_music(repo) == 1


def test_manifest_coverage_works_outside_music_too(repo: Path, fixtures: Path) -> None:
    """A curated set is legitimate wherever it lives, provided it carries evidence."""
    candidates = repo / "curation" / "candidates"
    add_midi(repo, fixtures, "curation/candidates/cleared.mid")
    add_manifest(candidates, ["cleared.mid"])

    assert audit_tracked_music(repo) == []


def test_a_manifest_row_marked_personal_still_cannot_publish_a_file(
    repo: Path, fixtures: Path
) -> None:
    """The correction that prompted this change.

    Recording that a candidate was rejected is right; shipping its bytes anyway
    would redistribute exactly what the row says may not be redistributed.
    """
    candidates = repo / "curation" / "candidates"
    add_midi(repo, fixtures, "curation/candidates/rejected.mid")
    add_manifest(
        candidates,
        ["rejected.mid"],
        rights_status="personal",
        license="all-rights-reserved",
        redistribution="prohibited",
    )

    offenders = audit_tracked_music(repo)
    assert len(offenders) == 1
    assert "not redistributable" in offenders[0]


# ------------------------------------------------------------- failing loudly


def test_a_tree_git_cannot_read_is_fatal_rather_than_empty(tmp_path: Path) -> None:
    """A rights check that silently finds nothing reports success.

    That is the one result it must never produce by accident, so being unable to
    enumerate has to be an error rather than a clean run.
    """
    with pytest.raises(NotATrackedTreeError, match="must run inside a Git checkout"):
        audit_tracked_music(tmp_path / "not-a-repo")


def test_the_auditor_itself_takes_any_list_of_paths(tmp_path: Path, fixtures: Path) -> None:
    """Enumeration and auditing stay separable, so a candidate set can be
    checked before anyone commits it."""
    assert audit_music_files([fixtures / "single-note.mid"])
    assert audit_music_files([]) == []


def test_non_midi_tracked_files_are_ignored(repo: Path, fixtures: Path) -> None:
    (repo / "notes.txt").write_text("not music", encoding="utf-8")
    git(repo, "add", "notes.txt")
    assert tracked_midi_files(repo) == []


def test_both_midi_extensions_are_covered(repo: Path, fixtures: Path) -> None:
    add_midi(repo, fixtures, "music/a.mid")
    add_midi(repo, fixtures, "music/b.midi")
    assert len(tracked_midi_files(repo)) == 2
    assert len(audit_tracked_music(repo)) == 2


def test_this_repository_currently_publishes_no_unevidenced_midi() -> None:
    """The live contract, run against the real checkout."""
    assert audit_tracked_music(Path(__file__).resolve().parents[1]) == []
