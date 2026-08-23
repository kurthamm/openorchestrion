"""Rights evidence, and the audit that decides whether a claim is supported.

``verified-open`` is the assertion that decides what this project is willing to
redistribute. Before this model existed the importer accepted that claim with a
null source, null license and null attribution, so a researched claim and a
hopeful one were indistinguishable in the sidecar and therefore in the catalog.

These tests pin the refusals rather than the successes: the value of the audit
is entirely in what it declines to write.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from openorchestrion.library.catalog import rebuild_catalog, search_catalog
from openorchestrion.library.importer import import_paths
from openorchestrion.library.policy import audit_committed_music
from openorchestrion.library.metadata import (
    MetadataConflictError,
    MetadataValidationError,
    read_rights,
    set_rights,
)
from openorchestrion.library.rights import (
    ESTABLISHED_LICENSES,
    RightsError,
    RightsEvidence,
    audit,
    implied_redistribution,
    normalize,
    verify,
)
from openorchestrion.testing.midi_fixtures import SUITE_RIGHTS, generate_suite

SCHEMAS = Path(__file__).resolve().parents[1] / "schemas"


# A claim that stands on its evidence, used as the baseline the failure cases
# each break in exactly one way.
SOUND = RightsEvidence(
    rights_status="verified-open",
    source_reference="https://example.org/scores/rag.mid",
    source_label="Example Archive",
    license="CC0-1.0",
    license_url="https://creativecommons.org/publicdomain/zero/1.0/",
    composition_rights="public-domain",
    composition_rights_basis="Composer died 1917; first published 1899",
    redistribution="permitted",
    verified_at="2026-08-23T00:00:00+00:00",
    verified_by="curation pass 1",
)


@pytest.fixture
def fixtures(tmp_path: Path) -> Path:
    source = tmp_path / "fixtures"
    generate_suite(source, long_run_minutes=1)
    return source


@pytest.fixture
def library(tmp_path: Path, fixtures: Path) -> Path:
    root = tmp_path / "library"
    assert not import_paths([fixtures], root).failed
    rebuild_catalog(root)
    return root


@pytest.fixture
def asset_id(library: Path) -> str:
    return search_catalog(library / "catalog.db", limit=1)[0]["asset_id"]


# ------------------------------------------------------ nothing to prove


@pytest.mark.parametrize("status", ["personal", "unknown"])
def test_a_claim_that_asserts_nothing_needs_no_evidence(status: str) -> None:
    """Most of a real library is personal. Research is not owed for it."""
    assert audit(RightsEvidence(rights_status=status)) == ()


def test_an_unrecognized_status_is_rejected_outright() -> None:
    assert audit(RightsEvidence(rights_status="probably-fine"))


# ------------------------------------------------------- the sound claim


def test_fully_evidenced_claim_is_accepted() -> None:
    assert audit(SOUND) == ()
    verify(SOUND)


def test_attribution_licenses_are_accepted_when_the_credit_is_recorded() -> None:
    evidence = RightsEvidence(
        rights_status="verified-open",
        source_reference="https://example.org/scores/nocturne.mid",
        license="CC-BY-SA-4.0",
        attribution="Typeset by A. Curator, CC BY-SA 4.0",
        composition_rights="public-domain",
        composition_rights_basis="Composer died 1849",
        redistribution="permitted-with-attribution",
    )
    assert audit(evidence) == ()


# ---------------------------------------------------------- the refusals


def _reasons(**overrides: object) -> str:
    from dataclasses import replace

    return " ".join(audit(replace(SOUND, **overrides)))


def test_a_claim_without_a_source_cannot_be_rechecked() -> None:
    assert "source_reference is required" in _reasons(source_reference=None)


def test_a_blank_source_is_not_a_source() -> None:
    assert "source_reference is required" in _reasons(source_reference="   ")


@pytest.mark.parametrize("rights", ["unknown", "in-copyright"])
def test_the_composition_must_be_established(rights: str) -> None:
    assert "composition_rights must be established" in _reasons(composition_rights=rights)


def test_public_domain_needs_a_stated_basis() -> None:
    """A bare 'public domain' is an opinion; the basis makes it reviewable."""
    assert "composition_rights_basis is required" in _reasons(composition_rights_basis=None)


def test_a_licensed_composition_needs_no_public_domain_basis() -> None:
    assert audit(
        RightsEvidence(
            rights_status="verified-open",
            source_reference="https://example.org/x.mid",
            license="CC0-1.0",
            composition_rights="licensed",
            redistribution="permitted",
        )
    ) == ()


def test_the_file_needs_its_own_license_even_when_the_composition_is_clear() -> None:
    """The whole point of separating the two questions.

    A public-domain composition sequenced by someone in 2003 is a new work, and
    that person may reserve every right in it.
    """
    reasons = _reasons(license=None)
    assert "license is required" in reasons
    assert "separate work" in reasons


def test_an_unfamiliar_license_is_not_read_as_permission() -> None:
    """The characteristic MIDI-archive string, which grants nothing at all."""
    reasons = _reasons(license="Free for personal use")
    assert "not one this project has established terms for" in reasons


def test_a_known_restrictive_license_is_refused() -> None:
    assert "does not permit redistribution" in _reasons(license="all-rights-reserved")


def test_a_noncommercial_license_is_refused() -> None:
    assert "does not permit redistribution" in _reasons(license="CC-BY-NC-4.0")


def test_a_redistribution_claim_contradicting_the_license_is_refused() -> None:
    """One of the two fields is wrong, and guessing which would defeat the point."""
    reasons = _reasons(license="CC-BY-4.0", redistribution="permitted", attribution="A. Curator")
    assert "implies 'permitted-with-attribution'" in reasons


def test_attribution_text_is_required_when_the_license_demands_credit() -> None:
    reasons = _reasons(
        license="CC-BY-4.0", redistribution="permitted-with-attribution", attribution=None
    )
    assert "attribution text is required" in reasons


def test_prohibited_redistribution_is_refused_even_with_a_permissive_license() -> None:
    assert "redistribution must be established" in _reasons(redistribution="prohibited")


def test_verify_raises_and_names_every_missing_piece() -> None:
    with pytest.raises(RightsError) as caught:
        verify(RightsEvidence(rights_status="verified-open"))
    message = str(caught.value)
    assert "source_reference" in message
    assert "license" in message
    assert "composition_rights" in message


# ------------------------------------------------------------- the table


@pytest.mark.parametrize("license_id", ESTABLISHED_LICENSES)
def test_every_established_license_permits_redistribution(license_id: str) -> None:
    assert implied_redistribution(license_id) in {"permitted", "permitted-with-attribution"}


def test_an_absent_license_id_is_unestablished_rather_than_restrictive() -> None:
    assert implied_redistribution("Apache-2.0") == "unknown"
    assert implied_redistribution(None) == "unknown"


# -------------------------------------------------------- reading it back


def test_a_sidecar_written_before_this_model_reads_as_unestablished() -> None:
    """Legacy provenance carried only five fields. Absence is not clearance."""
    legacy = {
        "imported_at": "2026-01-01T00:00:00+00:00",
        "rights_status": "personal",
        "source_reference": None,
        "source_label": None,
        "license": None,
        "attribution": None,
    }
    evidence = RightsEvidence.from_mapping(legacy)
    assert evidence.composition_rights == "unknown"
    assert evidence.redistribution == "unknown"


def test_an_unrecognized_provenance_field_is_an_error_not_a_silent_drop() -> None:
    with pytest.raises(RightsError, match="unknown provenance field"):
        RightsEvidence.from_mapping({"rights_status": "personal", "rights_notes": "hmm"})


def test_normalize_rejects_an_unknown_field() -> None:
    with pytest.raises(RightsError, match="unknown rights field"):
        normalize({"licence": "CC0-1.0"})


def test_normalize_rejects_an_invalid_enum() -> None:
    with pytest.raises(RightsError, match="redistribution must be one of"):
        normalize({"redistribution": "probably"})


def test_normalize_blanks_whitespace_to_null() -> None:
    assert normalize({"attribution": "  "})["attribution"] is None


# ---------------------------------------------------------- at import time


def test_the_importer_refuses_an_unevidenced_claim(tmp_path: Path, fixtures: Path) -> None:
    with pytest.raises(RightsError):
        import_paths(
            [fixtures], tmp_path / "library", rights=RightsEvidence(rights_status="verified-open")
        )


def test_a_refused_claim_writes_nothing_at_all(tmp_path: Path, fixtures: Path) -> None:
    """A rights failure must not leave a half-imported library behind."""
    library = tmp_path / "library"
    with pytest.raises(RightsError):
        import_paths(
            [fixtures], library, rights=RightsEvidence(rights_status="verified-open")
        )
    assert not (library / "assets").exists()


def test_the_claim_is_audited_once_rather_than_per_file(tmp_path: Path, fixtures: Path) -> None:
    """An unsupported claim is a mistake about the run, not about any one file.

    Per-file problems are reported as data in the report, by design — one bad
    download must not cost the caller the rest of the collection. A bad rights
    claim is the opposite: reported that way it would arrive as a dozen
    identical failures with the real problem buried in the repetition, so it
    raises instead. This pins the contrast rather than either half alone.
    """
    (fixtures / "truncated.mid").write_bytes(b"MThd\x00")

    report = import_paths([fixtures], tmp_path / "per-file")
    assert [failure.source for failure in report.failed] == [str(fixtures / "truncated.mid")]
    assert report.imported

    with pytest.raises(RightsError):
        import_paths(
            [fixtures], tmp_path / "run-level", rights=RightsEvidence(rights_status="verified-open")
        )


def test_an_evidenced_import_stores_the_whole_record(tmp_path: Path, fixtures: Path) -> None:
    library = tmp_path / "library"
    report = import_paths([fixtures / "single-note.mid"], library, rights=SOUND)
    assert not report.failed

    stored = json.loads(Path(report.imported[0].metadata_path).read_text())["provenance"]
    assert stored["rights_status"] == "verified-open"
    assert stored["composition_rights_basis"] == SOUND.composition_rights_basis
    assert stored["redistribution"] == "permitted"
    assert stored["imported_at"]


def test_an_evidenced_sidecar_validates_against_the_published_schema(
    tmp_path: Path, fixtures: Path
) -> None:
    library = tmp_path / "library"
    report = import_paths([fixtures / "single-note.mid"], library, rights=SOUND)
    document = json.loads(Path(report.imported[0].metadata_path).read_text())

    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((SCHEMAS / "midi-asset.schema.json").read_text())
    provenance = schema["properties"]["provenance"]
    jsonschema.validators.validator_for(provenance)(provenance).validate(document["provenance"])


def test_personal_remains_the_default(tmp_path: Path, fixtures: Path) -> None:
    """Importing someone's own collection must never assert redistribution."""
    library = tmp_path / "library"
    report = import_paths([fixtures / "single-note.mid"], library)
    stored = json.loads(Path(report.imported[0].metadata_path).read_text())["provenance"]
    assert stored["rights_status"] == "personal"
    assert stored["redistribution"] == "unknown"


# --------------------------------------------------- revising a claim later


def test_rights_can_be_established_after_import(library: Path, asset_id: str) -> None:
    """Research genuinely arrives after the bytes do."""
    record = set_rights(
        library,
        asset_id,
        {
            "rights_status": "verified-open",
            "source_reference": "https://example.org/scores/rag.mid",
            "license": "CC0-1.0",
            "composition_rights": "public-domain",
            "composition_rights_basis": "Composer died 1917",
            "redistribution": "permitted",
        },
    )
    assert record.provenance["rights_status"] == "verified-open"
    assert read_rights(library, asset_id).provenance["license"] == "CC0-1.0"


def test_a_later_claim_cannot_outrun_its_evidence(library: Path, asset_id: str) -> None:
    """The audit runs against the merged block, not the changes alone."""
    with pytest.raises(MetadataValidationError, match="verified-open"):
        set_rights(library, asset_id, {"rights_status": "verified-open"})


def test_a_refused_revision_leaves_the_stored_claim_intact(library: Path, asset_id: str) -> None:
    before = read_rights(library, asset_id).provenance
    with pytest.raises(MetadataValidationError):
        set_rights(library, asset_id, {"rights_status": "verified-open"})
    assert read_rights(library, asset_id).provenance == before


def test_the_import_timestamp_survives_a_revision(library: Path, asset_id: str) -> None:
    imported_at = read_rights(library, asset_id).provenance["imported_at"]
    set_rights(library, asset_id, {"source_label": "Example Archive"})
    assert read_rights(library, asset_id).provenance["imported_at"] == imported_at


def test_the_import_timestamp_is_not_editable(library: Path, asset_id: str) -> None:
    with pytest.raises(MetadataValidationError, match="imported_at"):
        set_rights(library, asset_id, {"imported_at": "2000-01-01T00:00:00+00:00"})


def test_a_revision_respects_optimistic_concurrency(library: Path, asset_id: str) -> None:
    stale = read_rights(library, asset_id).revision
    set_rights(library, asset_id, {"source_label": "First"})
    with pytest.raises(MetadataConflictError):
        set_rights(library, asset_id, {"source_label": "Second"}, expected_revision=stale)


def test_curated_metadata_is_untouched_by_a_rights_revision(library: Path, asset_id: str) -> None:
    from openorchestrion.library.metadata import read_metadata, update_metadata

    update_metadata(library, asset_id, {"title": "Kept", "favorite": True})
    set_rights(library, asset_id, {"source_label": "Example Archive"})

    curated = read_metadata(library, asset_id).descriptive_metadata
    assert curated["title"] == "Kept"
    assert curated["favorite"] is True


def test_a_downgrade_to_personal_is_always_allowed(library: Path, asset_id: str) -> None:
    """Withdrawing a claim needs no evidence. Only asserting one does."""
    set_rights(
        library,
        asset_id,
        {
            "rights_status": "verified-open",
            "source_reference": "https://example.org/x.mid",
            "license": "CC0-1.0",
            "composition_rights": "public-domain",
            "composition_rights_basis": "Composer died 1917",
            "redistribution": "permitted",
        },
    )
    record = set_rights(library, asset_id, {"rights_status": "personal"})
    assert record.provenance["rights_status"] == "personal"


# ------------------------------------------------------ through the catalog


def test_an_established_claim_reaches_the_catalog(library: Path, asset_id: str) -> None:
    """Rights gate what a station may play, so the index must agree with the sidecar."""
    set_rights(
        library,
        asset_id,
        {
            "rights_status": "verified-open",
            "source_reference": "https://example.org/x.mid",
            "license": "CC0-1.0",
            "composition_rights": "public-domain",
            "composition_rights_basis": "Composer died 1917",
            "redistribution": "permitted",
        },
    )
    rebuild_catalog(library)
    rows = search_catalog(library / "catalog.db", rights_status="verified-open", limit=100)
    assert [row["asset_id"] for row in rows] == [asset_id]


def test_the_sidecar_stays_the_source_of_truth(library: Path, asset_id: str) -> None:
    """Deleting the catalog loses nothing: the rights record survives a rebuild."""
    set_rights(library, asset_id, {"source_label": "Example Archive"})
    (library / "catalog.db").unlink()
    rebuild_catalog(library)
    assert read_rights(library, asset_id).provenance["source_label"] == "Example Archive"


# ------------------------------------------------------------- at the CLI


def _import(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-W", "ignore", "-m", "openorchestrion.library.importer", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_cli_refuses_an_unevidenced_claim(tmp_path: Path, fixtures: Path) -> None:
    result = _import(
        str(fixtures / "single-note.mid"),
        "--library-root",
        str(tmp_path / "library"),
        "--rights-status",
        "verified-open",
    )
    assert result.returncode == 2
    assert "not supported by the recorded evidence" in result.stderr
    assert not (tmp_path / "library" / "assets").exists()


def test_the_cli_accepts_a_complete_record(tmp_path: Path, fixtures: Path) -> None:
    library = tmp_path / "library"
    result = _import(
        str(fixtures / "single-note.mid"),
        "--library-root",
        str(library),
        "--rights-status",
        "verified-open",
        "--source-reference",
        "https://example.org/scores/rag.mid",
        "--source-label",
        "Example Archive",
        "--license",
        "CC0-1.0",
        "--composition-rights",
        "public-domain",
        "--composition-rights-basis",
        "Composer died 1917",
        "--redistribution",
        "permitted",
    )
    assert result.returncode == 0, result.stderr
    sidecar = next((library / "assets").glob("*.json"))
    assert json.loads(sidecar.read_text())["provenance"]["rights_status"] == "verified-open"


@pytest.mark.parametrize(
    "damage",
    [
        pytest.param(None, id="no-sidecar"),
        pytest.param("personal", id="not-redistributable"),
        pytest.param("verified-open", id="claim-without-evidence"),
    ],
)
def test_the_repository_refuses_midi_without_established_rights(
    tmp_path: Path, fixtures: Path, damage: str | None
) -> None:
    """The policy is only worth as much as the check behind it.

    Committing someone's collection is one convenient ``git add`` away, and in a
    large diff nobody sees it. This is the guard, so it is tested against each
    way a file can arrive without rights rather than only against the clean tree.
    """
    music = tmp_path / "repo" / "music"
    music.mkdir(parents=True)

    midi = music / "smuggled.mid"
    midi.write_bytes((fixtures / "single-note.mid").read_bytes())
    if damage is not None:
        report = import_paths([midi], tmp_path / "staging")
        document = json.loads(Path(report.imported[0].metadata_path).read_text())
        document["provenance"]["rights_status"] = damage
        midi.with_suffix(".json").write_text(json.dumps(document, indent=2))

    offenders = audit_committed_music(music)
    assert len(offenders) == 1
    assert "smuggled.mid" in offenders[0]


def test_the_repository_accepts_midi_that_carries_its_evidence(
    tmp_path: Path, fixtures: Path
) -> None:
    music = tmp_path / "repo" / "music"
    music.mkdir(parents=True)

    midi = music / "cleared.mid"
    midi.write_bytes((fixtures / "single-note.mid").read_bytes())
    report = import_paths([midi], tmp_path / "staging", rights=SOUND)
    midi.with_suffix(".json").write_text(Path(report.imported[0].metadata_path).read_text())

    assert audit_committed_music(music) == []


def test_the_repository_currently_commits_no_third_party_midi() -> None:
    """The starter catalog is assembled on the appliance, not committed here."""
    assert audit_committed_music(Path(__file__).resolve().parents[1] / "music") == []


def test_the_generated_fixtures_carry_a_real_record() -> None:
    """The conformance suite is the project's own output, so its terms are ours.

    The repository contract check imports it as ``verified-open``; that claim now
    has to survive the same audit as anything else.
    """
    assert audit(SUITE_RIGHTS) == ()
    assert SUITE_RIGHTS.attribution

