"""Importing a curated set, where every file carries its own evidence.

``import_paths`` applies one rights record to a whole run, which is right for
"import my collection" and wrong for a starter catalog. A curated set is
precisely a set where every file has a different source, a different license and
a different composer, so evidence applied per directory is not evidence at all —
it is a guess averaged over a folder.

The manifest is curation *input*. What it produces is ordinary sidecars written
by the ordinary importer, so nothing downstream learns a second format.
"""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from openorchestrion.library.policy import audit_committed_music
from openorchestrion.library.importer import (
    ManifestError,
    import_manifest,
    read_curation_manifest,
)
from openorchestrion.testing.midi_fixtures import generate_suite

COLUMNS = (
    "path",
    "sha256",
    "rights_status",
    "source_reference",
    "source_label",
    "license",
    "license_url",
    "attribution",
    "composition_rights",
    "composition_rights_basis",
    "redistribution",
    "verified_by",
)

CLEARED = {
    "rights_status": "verified-open",
    "source_reference": "https://example.org/scores/rag.mid",
    "source_label": "Example Archive",
    "license": "CC0-1.0",
    "composition_rights": "public-domain",
    "composition_rights_basis": "Composer died 1917; published 1899",
    "redistribution": "permitted",
}


@pytest.fixture
def fixtures(tmp_path: Path) -> Path:
    source = tmp_path / "fixtures"
    generate_suite(source, long_run_minutes=1)
    return source


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_manifest(path: Path, rows: list[dict[str, str]]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in COLUMNS})
    return path


# ------------------------------------------------------------- reading it


def test_a_manifest_carries_evidence_per_row(tmp_path: Path, fixtures: Path) -> None:
    manifest = write_manifest(
        tmp_path / "m.csv",
        [
            {"path": "single-note.mid", **CLEARED},
            {
                "path": "two-piano-split.mid",
                **CLEARED,
                "license": "CC-BY-SA-4.0",
                "attribution": "Typeset by A. Curator, CC BY-SA 4.0",
                "redistribution": "permitted-with-attribution",
                "composition_rights_basis": "Composer died 1791",
            },
        ],
    )
    entries = read_curation_manifest(manifest)

    assert [entry.path for entry in entries] == ["single-note.mid", "two-piano-split.mid"]
    assert entries[0].rights.license == "CC0-1.0"
    assert entries[1].rights.license == "CC-BY-SA-4.0"
    assert entries[1].rights.attribution


def test_blank_cells_are_omitted_rather_than_written(tmp_path: Path) -> None:
    """A spreadsheet exported with every column must not stamp empty strings."""
    manifest = write_manifest(tmp_path / "m.csv", [{"path": "a.mid", **CLEARED}])
    entry = read_curation_manifest(manifest)[0]
    assert entry.rights.attribution is None
    assert entry.rights.verified_by is None


def test_rows_without_a_path_are_skipped(tmp_path: Path) -> None:
    """Trailing blank lines are what spreadsheets export, not an error."""
    manifest = write_manifest(tmp_path / "m.csv", [{"path": "a.mid", **CLEARED}, {"path": ""}])
    assert len(read_curation_manifest(manifest)) == 1


def test_a_manifest_without_a_path_column_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "m.csv"
    path.write_text("sha256,license\nabc,CC0-1.0\n", encoding="utf-8")
    with pytest.raises(ManifestError, match="needs a 'path' column"):
        read_curation_manifest(path)


def test_an_unknown_column_is_refused_and_names_the_alternatives(tmp_path: Path) -> None:
    """A misspelled evidence column would otherwise be silently dropped.

    Losing 'attribution' to a typo means shipping a file without the credit its
    license requires, which is the failure this whole model exists to prevent.
    """
    path = tmp_path / "m.csv"
    path.write_text("path,licence\na.mid,CC0-1.0\n", encoding="utf-8")
    with pytest.raises(ManifestError) as caught:
        read_curation_manifest(path)
    assert "licence" in str(caught.value)
    assert "composition_rights_basis" in str(caught.value)


def test_an_invalid_enum_names_the_row(tmp_path: Path) -> None:
    manifest = write_manifest(
        tmp_path / "m.csv", [{"path": "a.mid", **CLEARED, "redistribution": "probably"}]
    )
    with pytest.raises(ManifestError, match="row 2"):
        read_curation_manifest(manifest)


def test_an_empty_manifest_is_not_an_error(tmp_path: Path) -> None:
    manifest = write_manifest(tmp_path / "m.csv", [])
    assert read_curation_manifest(manifest) == []


def test_a_missing_manifest_says_so(tmp_path: Path) -> None:
    with pytest.raises(ManifestError, match="cannot be read"):
        read_curation_manifest(tmp_path / "nope.csv")


# ------------------------------------------------------------- importing


def test_each_file_lands_under_its_own_evidence(tmp_path: Path, fixtures: Path) -> None:
    manifest = write_manifest(
        tmp_path / "m.csv",
        [
            {"path": "single-note.mid", **CLEARED},
            {
                "path": "two-piano-split.mid",
                **CLEARED,
                "source_reference": "https://example.org/other",
                "license": "CC-BY-SA-4.0",
                "attribution": "Typeset by A. Curator, CC BY-SA 4.0",
                "redistribution": "permitted-with-attribution",
            },
        ],
    )
    report = import_manifest(
        read_curation_manifest(manifest), tmp_path / "library", base_dir=fixtures
    )
    assert not report.failed

    stored = {}
    for result in report.imported:
        provenance = json.loads(Path(result.metadata_path).read_text())["provenance"]
        stored[provenance["source_reference"]] = provenance

    assert stored["https://example.org/scores/rag.mid"]["license"] == "CC0-1.0"
    assert stored["https://example.org/scores/rag.mid"]["attribution"] is None
    assert stored["https://example.org/other"]["license"] == "CC-BY-SA-4.0"
    assert stored["https://example.org/other"]["attribution"]


def test_one_unsupported_claim_does_not_cost_the_rest(tmp_path: Path, fixtures: Path) -> None:
    """The rest of the research is still good.

    Re-running after a fix must not re-litigate what already landed, and content
    addressing makes that safe.
    """
    manifest = write_manifest(
        tmp_path / "m.csv",
        [
            {"path": "single-note.mid", **CLEARED},
            {"path": "gm-ensemble.mid", **CLEARED, "license": "Free for personal use"},
            {"path": "sustain-cc64.mid", **CLEARED},
        ],
    )
    report = import_manifest(
        read_curation_manifest(manifest), tmp_path / "library", base_dir=fixtures
    )

    assert len(report.imported) == 2
    assert len(report.failed) == 1
    assert report.failed[0].error_type == "RightsError"
    assert "row 3" in report.failed[0].source


def test_a_failing_row_names_its_line_in_the_manifest(tmp_path: Path, fixtures: Path) -> None:
    """A curator fixing a 40-row spreadsheet needs the row, not just the file."""
    manifest = write_manifest(
        tmp_path / "m.csv",
        [
            {"path": "single-note.mid", **CLEARED},
            {"path": "missing.mid", **CLEARED},
        ],
    )
    report = import_manifest(
        read_curation_manifest(manifest), tmp_path / "library", base_dir=fixtures
    )
    assert report.failed[0].source.startswith("row 3: missing.mid")


# ------------------------------------------------------- the digest guard


def test_a_file_matching_its_researched_digest_is_accepted(
    tmp_path: Path, fixtures: Path
) -> None:
    manifest = write_manifest(
        tmp_path / "m.csv",
        [
            {
                "path": "single-note.mid",
                "sha256": digest(fixtures / "single-note.mid"),
                **CLEARED,
            }
        ],
    )
    report = import_manifest(
        read_curation_manifest(manifest), tmp_path / "library", base_dir=fixtures
    )
    assert not report.failed


def test_a_file_that_is_not_the_researched_one_is_refused(
    tmp_path: Path, fixtures: Path
) -> None:
    """The claim was researched against specific bytes.

    Whoever read the license and whatever machine imports the file are usually
    not the same, and different bytes may be a different arrangement under
    different terms. This is a rights failure, not a checksum nicety.
    """
    manifest = write_manifest(
        tmp_path / "m.csv",
        [
            {
                "path": "single-note.mid",
                # The digest of a different fixture entirely.
                "sha256": digest(fixtures / "gm-ensemble.mid"),
                **CLEARED,
            }
        ],
    )
    report = import_manifest(
        read_curation_manifest(manifest), tmp_path / "library", base_dir=fixtures
    )

    assert not report.imported
    assert "evidence was gathered about a different file" in report.failed[0].reason
    assert not (tmp_path / "library" / "assets").exists()


def test_the_digest_is_optional(tmp_path: Path, fixtures: Path) -> None:
    """Not every source publishes one; its absence must not block curation."""
    manifest = write_manifest(tmp_path / "m.csv", [{"path": "single-note.mid", **CLEARED}])
    entry = read_curation_manifest(manifest)[0]
    assert entry.expected_sha256 is None
    assert not import_manifest([entry], tmp_path / "library", base_dir=fixtures).failed


def test_a_digest_is_compared_case_insensitively(tmp_path: Path, fixtures: Path) -> None:
    manifest = write_manifest(
        tmp_path / "m.csv",
        [
            {
                "path": "single-note.mid",
                "sha256": digest(fixtures / "single-note.mid").upper(),
                **CLEARED,
            }
        ],
    )
    report = import_manifest(
        read_curation_manifest(manifest), tmp_path / "library", base_dir=fixtures
    )
    assert not report.failed


# --------------------------------------------------------------- the CLI


def _import(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-W", "ignore", "-m", "openorchestrion.library.importer", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_cli_imports_a_manifest(tmp_path: Path, fixtures: Path) -> None:
    manifest = write_manifest(
        fixtures / "m.csv", [{"path": "single-note.mid", **CLEARED}]
    )
    result = _import("--from-csv", str(manifest), "--library-root", str(tmp_path / "library"))

    assert result.returncode == 0, result.stderr
    sidecar = next((tmp_path / "library" / "assets").glob("*.json"))
    assert json.loads(sidecar.read_text())["provenance"]["rights_status"] == "verified-open"


def test_the_cli_resolves_paths_relative_to_the_manifest(
    tmp_path: Path, fixtures: Path
) -> None:
    """A manifest travels with its files; the curator's shell directory is incidental."""
    manifest = write_manifest(fixtures / "m.csv", [{"path": "single-note.mid", **CLEARED}])
    result = _import("--from-csv", str(manifest), "--library-root", str(tmp_path / "library"))
    assert result.returncode == 0, result.stderr


def test_the_cli_exits_non_zero_on_a_partial_run(tmp_path: Path, fixtures: Path) -> None:
    """A scripted curation run must not look successful because most rows parsed."""
    manifest = write_manifest(
        fixtures / "m.csv",
        [
            {"path": "single-note.mid", **CLEARED},
            {"path": "gm-ensemble.mid", **CLEARED, "license": "Free for personal use"},
        ],
    )
    result = _import("--from-csv", str(manifest), "--library-root", str(tmp_path / "library"))
    assert result.returncode == 1
    assert "skipped" in result.stdout


def test_the_cli_refuses_a_malformed_manifest(tmp_path: Path) -> None:
    path = tmp_path / "m.csv"
    path.write_text("path,licence\na.mid,CC0-1.0\n", encoding="utf-8")
    result = _import("--from-csv", str(path), "--library-root", str(tmp_path / "library"))
    assert result.returncode == 2
    assert "unknown column" in result.stderr


def test_the_cli_rejects_sources_and_manifest_together(tmp_path: Path, fixtures: Path) -> None:
    manifest = write_manifest(tmp_path / "m.csv", [{"path": "single-note.mid", **CLEARED}])
    result = _import(
        str(fixtures / "single-note.mid"),
        "--from-csv",
        str(manifest),
        "--library-root",
        str(tmp_path / "library"),
    )
    assert result.returncode == 2
    assert "not both" in result.stderr


def test_the_cli_still_requires_something_to_import(tmp_path: Path) -> None:
    result = _import("--library-root", str(tmp_path / "library"))
    assert result.returncode == 2


def test_the_ordinary_directory_import_is_unchanged(tmp_path: Path, fixtures: Path) -> None:
    """The common case keeps working: import a folder, get personal assets."""
    result = _import(str(fixtures), "--library-root", str(tmp_path / "library"))
    assert result.returncode == 0, result.stderr
    sidecars = list((tmp_path / "library" / "assets").glob("*.json"))
    assert len(sidecars) == 14
    assert json.loads(sidecars[0].read_text())["provenance"]["rights_status"] == "personal"


def test_a_manifest_row_can_stay_personal(tmp_path: Path, fixtures: Path) -> None:
    """Curation includes deciding something is not redistributable.

    A candidate whose file license turns out to be unusable still belongs in the
    library as a personal import; it just cannot join the starter set.
    """
    manifest = write_manifest(
        tmp_path / "m.csv",
        [
            {
                "path": "single-note.mid",
                "rights_status": "personal",
                "source_reference": "https://example.org/x",
                "license": "all-rights-reserved",
                "composition_rights": "public-domain",
                "composition_rights_basis": "Composer died 1917",
                "redistribution": "prohibited",
            }
        ],
    )
    report = import_manifest(
        read_curation_manifest(manifest), tmp_path / "library", base_dir=fixtures
    )
    assert not report.failed
    provenance = json.loads(Path(report.imported[0].metadata_path).read_text())["provenance"]
    assert provenance["rights_status"] == "personal"
    # The research is still recorded, so nobody repeats it.
    assert provenance["license"] == "all-rights-reserved"
    assert provenance["redistribution"] == "prohibited"


def test_manifest_values_are_normalized_before_they_are_stored(
    tmp_path: Path, fixtures: Path
) -> None:
    """Spreadsheets introduce stray whitespace; sidecars should not inherit it.

    A source reference with a trailing space still has to compare equal to the
    one a later re-check types in by hand.
    """
    manifest = write_manifest(
        tmp_path / "m.csv",
        [
            {
                "path": "single-note.mid",
                **CLEARED,
                "source_reference": "  https://example.org/padded  ",
                "verified_by": "   ",
            }
        ],
    )
    report = import_manifest(
        read_curation_manifest(manifest), tmp_path / "library", base_dir=fixtures
    )
    assert not report.failed

    provenance = json.loads(Path(report.imported[0].metadata_path).read_text())["provenance"]
    assert provenance["source_reference"] == "https://example.org/padded"
    assert provenance["verified_by"] is None


# ------------------------------------------- the manifest as committed evidence


def _commit(directory: Path, fixtures: Path, names: list[str], **overrides: str) -> Path:
    """A committed starter directory: the files, plus the manifest vouching for them."""
    directory.mkdir(parents=True, exist_ok=True)
    rows = []
    for name in names:
        shutil.copy2(fixtures / name, directory / name)
        rows.append(
            {
                "path": name,
                "sha256": digest(fixtures / name),
                **CLEARED,
                **overrides,
            }
        )
    write_manifest(directory / "catalog.csv", rows)
    return directory


def test_committed_music_may_be_vouched_for_by_its_manifest(
    tmp_path: Path, fixtures: Path
) -> None:
    """The manifest is what the installer reads, so it is what CI should check.

    A per-file sidecar committed alongside would be a second copy of the same
    assertion, free to drift from the one that actually takes effect.
    """
    music = tmp_path / "music"
    _commit(music / "starter", fixtures, ["single-note.mid", "two-piano-split.mid"])
    assert audit_committed_music(music) == []


def test_committed_music_with_neither_sidecar_nor_manifest_row_is_refused(
    tmp_path: Path, fixtures: Path
) -> None:
    music = tmp_path / "music"
    starter = _commit(music / "starter", fixtures, ["single-note.mid"])
    shutil.copy2(fixtures / "gm-ensemble.mid", starter / "gm-ensemble.mid")

    offenders = audit_committed_music(music)
    assert len(offenders) == 1
    assert "gm-ensemble.mid" in offenders[0]
    assert "no sidecar or manifest row" in offenders[0]


def test_a_manifest_row_that_does_not_clear_the_audit_is_refused(
    tmp_path: Path, fixtures: Path
) -> None:
    music = tmp_path / "music"
    _commit(music / "starter", fixtures, ["single-note.mid"], license="Free for personal use")

    offenders = audit_committed_music(music)
    assert len(offenders) == 1
    assert "not one this project has established terms for" in offenders[0]


def test_a_personal_manifest_row_cannot_smuggle_a_file_into_the_repository(
    tmp_path: Path, fixtures: Path
) -> None:
    """Recording research is not the same as clearing redistribution."""
    music = tmp_path / "music"
    _commit(
        music / "starter",
        fixtures,
        ["single-note.mid"],
        rights_status="personal",
        license="all-rights-reserved",
        redistribution="prohibited",
    )
    offenders = audit_committed_music(music)
    assert len(offenders) == 1
    assert "not redistributable" in offenders[0]


def test_swapping_a_committed_file_without_updating_its_row_is_caught(
    tmp_path: Path, fixtures: Path
) -> None:
    """How a starter catalog ends up shipping something nobody checked.

    The row keeps vouching for bytes that are no longer there, and every other
    check still passes, so without the digest comparison nothing notices.
    """
    music = tmp_path / "music"
    starter = _commit(music / "starter", fixtures, ["single-note.mid"])
    shutil.copy2(fixtures / "note-range.mid", starter / "single-note.mid")

    offenders = audit_committed_music(music)
    assert len(offenders) == 1
    assert "does not match the digest its manifest row records" in offenders[0]


def test_a_broken_manifest_surfaces_as_unestablished_rights(
    tmp_path: Path, fixtures: Path
) -> None:
    """Reported against the music, not as a parse error nobody connects to it."""
    music = tmp_path / "music"
    starter = _commit(music / "starter", fixtures, ["single-note.mid"])
    (starter / "catalog.csv").write_text("path,licence\nsingle-note.mid,CC0-1.0\n")

    offenders = audit_committed_music(music)
    assert len(offenders) == 1
    assert "no sidecar or manifest row" in offenders[0]


def test_a_sidecar_still_works_and_takes_precedence(tmp_path: Path, fixtures: Path) -> None:
    """The library's own durable format keeps working where it is used."""
    music = tmp_path / "music"
    starter = music / "starter"
    starter.mkdir(parents=True)
    shutil.copy2(fixtures / "single-note.mid", starter / "single-note.mid")

    report = import_manifest(
        [read_curation_manifest(
            write_manifest(tmp_path / "m.csv", [{"path": "single-note.mid", **CLEARED}])
        )[0]],
        tmp_path / "library",
        base_dir=fixtures,
    )
    (starter / "single-note.json").write_text(Path(report.imported[0].metadata_path).read_text())

    assert audit_committed_music(music) == []


def test_the_committed_layout_installs_with_its_evidence_intact(
    tmp_path: Path, fixtures: Path
) -> None:
    """The point of all of it.

    Committing files whose evidence the installer discards would give an
    appliance a starter catalog its own stations cannot see: imported as
    personal, invisible to every verified-open query.
    """
    starter = _commit(tmp_path / "music" / "starter", fixtures, ["single-note.mid"])

    report = import_manifest(
        read_curation_manifest(starter / "catalog.csv"),
        tmp_path / "library",
        base_dir=starter,
    )
    assert not report.failed

    provenance = json.loads(Path(report.imported[0].metadata_path).read_text())["provenance"]
    assert provenance["rights_status"] == "verified-open"
    assert provenance["license"] == "CC0-1.0"
