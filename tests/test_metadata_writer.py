"""Curated metadata editing.

The sidecar is the durable source of truth and catalog.db is disposable, so the
tests that matter most are the ones proving an edit survives the catalog being
deleted, and that an invalid edit never replaces a valid sidecar.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from openorchestrion.library.catalog import get_asset, rebuild_catalog, reindex_asset, search_catalog
from openorchestrion.library.importer import import_paths
from openorchestrion.library.metadata import (
    CURATED_FIELDS,
    AssetNotFoundError,
    MetadataConflictError,
    MetadataValidationError,
    apply_edits,
    normalize_asset_id,
    read_csv_edits,
    read_metadata,
    set_favorite,
    sidecar_path,
    update_metadata,
)
from openorchestrion.testing.midi_fixtures import generate_suite

SCHEMA = json.loads((Path(__file__).resolve().parents[1] / "schemas" / "midi-asset.schema.json").read_text())


@pytest.fixture
def library(tmp_path: Path) -> Path:
    root = tmp_path / "library"
    fixtures = tmp_path / "fixtures"
    generate_suite(fixtures, long_run_minutes=1)
    assert not import_paths([fixtures], root).failed
    rebuild_catalog(root)
    return root


@pytest.fixture
def asset_id(library: Path) -> str:
    return search_catalog(library / "catalog.db", limit=1)[0]["asset_id"]


# ------------------------------------------------------------- the basics


def test_import_leaves_metadata_empty_which_is_the_problem_this_solves(
    library: Path, asset_id: str
) -> None:
    assert read_metadata(library, asset_id).descriptive_metadata == {}


def test_curated_fields_round_trip(library: Path, asset_id: str) -> None:
    record = update_metadata(
        library,
        asset_id,
        {
            "title": "Maple Leaf Rag",
            "composer": "Scott Joplin",
            "era": "Ragtime",
            "year_composed": 1899,
            "genres": ["Ragtime"],
            "moods": ["lively"],
            "themes": ["cocktail"],
            "instrumentation": ["piano"],
            "tags": ["classic"],
            "performance_type": "SOLO_PIANO",
            "quality_grade": "A",
            "familiarity": "high",
            "energy": 4,
            "favorite": True,
        },
    )
    stored = read_metadata(library, asset_id).descriptive_metadata
    assert stored == record.descriptive_metadata
    assert stored["title"] == "Maple Leaf Rag"
    assert stored["familiarity"] == 5  # "high" normalizes to the catalog's scale
    assert stored["favorite"] is True


def test_edits_merge_rather_than_replace(library: Path, asset_id: str) -> None:
    update_metadata(library, asset_id, {"title": "Gymnopedie No. 1"})
    update_metadata(library, asset_id, {"composer": "Erik Satie"})
    stored = read_metadata(library, asset_id).descriptive_metadata
    assert stored["title"] == "Gymnopedie No. 1"
    assert stored["composer"] == "Erik Satie"


def test_clearing_a_field_removes_it(library: Path, asset_id: str) -> None:
    update_metadata(library, asset_id, {"title": "Temporary", "composer": "Kept"})
    update_metadata(library, asset_id, remove=["title"])
    stored = read_metadata(library, asset_id).descriptive_metadata
    assert "title" not in stored
    assert stored["composer"] == "Kept"


def test_free_text_is_normalized_not_restricted(library: Path, asset_id: str) -> None:
    """A hobbyist library will always carry tags nobody anticipated."""
    record = update_metadata(
        library,
        asset_id,
        {"genres": " Klezmer , sea shanty ,, Klezmer , KLEZMER "},
    )
    # Accepted as written, trimmed, blanks dropped, case-duplicates collapsed
    # onto the first spelling seen.
    assert record.descriptive_metadata["genres"] == ["Klezmer", "sea shanty"]


def test_asset_id_accepted_in_either_form(library: Path, asset_id: str) -> None:
    bare = asset_id.split(":", 1)[1]
    assert normalize_asset_id(bare) == asset_id
    update_metadata(library, bare, {"title": "By bare digest"})
    assert read_metadata(library, asset_id).descriptive_metadata["title"] == "By bare digest"


def test_unknown_asset_is_reported_clearly(library: Path) -> None:
    with pytest.raises(AssetNotFoundError):
        read_metadata(library, "sha256:" + "0" * 64)


# ------------------------------------------- invalid edits never overwrite


@pytest.mark.parametrize(
    "changes",
    [
        {"title": ""},
        {"title": 42},
        {"year_composed": 0},
        {"year_composed": "not a year"},
        {"familiarity": 9},
        {"energy": "enormous"},
        {"performance_type": "ORCHESTRA"},
        {"quality_grade": "F"},
        {"favorite": "maybe"},
        {"genres": [1, 2]},
        {"rights_status": "verified-open"},
        {"unknown_field": "x"},
    ],
)
def test_invalid_metadata_never_replaces_the_previous_sidecar(
    library: Path, asset_id: str, changes: dict
) -> None:
    update_metadata(library, asset_id, {"title": "Known Good", "composer": "Real Composer"})
    before = sidecar_path(library, asset_id).read_bytes()

    with pytest.raises(MetadataValidationError):
        update_metadata(library, asset_id, changes)

    assert sidecar_path(library, asset_id).read_bytes() == before
    assert read_metadata(library, asset_id).descriptive_metadata["title"] == "Known Good"


def test_a_bad_field_does_not_apply_the_good_ones_alongside_it(
    library: Path, asset_id: str
) -> None:
    """The whole change set validates before anything is written."""
    with pytest.raises(MetadataValidationError):
        update_metadata(library, asset_id, {"composer": "Valid", "quality_grade": "Z"})
    assert read_metadata(library, asset_id).descriptive_metadata == {}


def test_rights_and_provenance_cannot_be_upgraded_by_a_curation_edit(
    library: Path, asset_id: str
) -> None:
    document = json.loads(sidecar_path(library, asset_id).read_text())
    assert document["provenance"]["rights_status"] == "personal"

    for blocked in ("provenance", "deterministic_analysis", "ai_enrichment", "file"):
        with pytest.raises(MetadataValidationError, match="cannot be edited here|unknown"):
            update_metadata(library, asset_id, {blocked: {"rights_status": "verified-open"}})

    after = json.loads(sidecar_path(library, asset_id).read_text())
    assert after["provenance"] == document["provenance"]


def test_deterministic_analysis_survives_curation(library: Path, asset_id: str) -> None:
    before = json.loads(sidecar_path(library, asset_id).read_text())["deterministic_analysis"]
    update_metadata(library, asset_id, {"title": "Curated", "favorite": True})
    after = json.loads(sidecar_path(library, asset_id).read_text())["deterministic_analysis"]
    assert after == before


# ------------------------------------------------ optimistic concurrency


def test_a_stale_editor_cannot_silently_overwrite_a_fresh_one(
    library: Path, asset_id: str
) -> None:
    both_read = read_metadata(library, asset_id).revision

    update_metadata(library, asset_id, {"title": "First writer"}, expected_revision=both_read)

    with pytest.raises(MetadataConflictError) as caught:
        update_metadata(library, asset_id, {"title": "Second writer"}, expected_revision=both_read)

    assert caught.value.expected == both_read
    # The first writer's edit stands; the second was refused, not merged.
    assert read_metadata(library, asset_id).descriptive_metadata["title"] == "First writer"


def test_the_revision_from_a_successful_write_is_usable_immediately(
    library: Path, asset_id: str
) -> None:
    first = update_metadata(library, asset_id, {"title": "One"})
    second = update_metadata(
        library, asset_id, {"title": "Two"}, expected_revision=first.revision
    )
    assert second.revision != first.revision
    assert read_metadata(library, asset_id).revision == second.revision


def test_omitting_the_revision_forces_the_write(library: Path, asset_id: str) -> None:
    read_metadata(library, asset_id)
    update_metadata(library, asset_id, {"title": "Forced"})
    assert read_metadata(library, asset_id).descriptive_metadata["title"] == "Forced"


# --------------------------------------- durability across catalog rebuild


def test_metadata_survives_deleting_the_catalog(library: Path, asset_id: str) -> None:
    """catalog.db is disposable; the sidecar is the durable source of truth."""
    update_metadata(
        library,
        asset_id,
        {"title": "Survives", "composer": "Durable", "genres": ["ragtime"], "favorite": True},
    )
    reindex_asset(library / "catalog.db", library, asset_id)

    (library / "catalog.db").unlink()
    assert not (library / "catalog.db").exists()

    rebuild_catalog(library)
    row = get_asset(library / "catalog.db", asset_id)
    assert row is not None
    assert row["title"] == "Survives"
    assert row["composer"] == "Durable"
    assert row["favorite"] is True
    assert row["genres"] == ["ragtime"]


def test_reindex_brings_the_catalog_into_step_without_a_full_rebuild(
    library: Path, asset_id: str
) -> None:
    update_metadata(library, asset_id, {"title": "Freshly tagged", "genres": ["jazz"]})
    assert get_asset(library / "catalog.db", asset_id)["title"] is None

    assert reindex_asset(library / "catalog.db", library, asset_id) is True
    row = get_asset(library / "catalog.db", asset_id)
    assert row["title"] == "Freshly tagged"
    assert row["genres"] == ["jazz"]


def test_reindex_is_a_no_op_without_a_catalog(library: Path, asset_id: str) -> None:
    (library / "catalog.db").unlink()
    assert reindex_asset(library / "catalog.db", library, asset_id) is False
    assert not (library / "catalog.db").exists()


def test_tagging_creates_a_composition_so_stations_have_something_to_match(
    library: Path, asset_id: str
) -> None:
    """The whole point: an untagged library gives Smart Stations nothing."""
    from openorchestrion.library.catalog import catalog_stats

    assert catalog_stats(library / "catalog.db")["compositions"] == 0
    update_metadata(library, asset_id, {"title": "The Entertainer", "composer": "Scott Joplin"})
    rebuild_catalog(library)
    assert catalog_stats(library / "catalog.db")["compositions"] == 1


# ------------------------------------------------------------- bulk / CSV


def test_csv_bulk_edit_keyed_by_sha256(library: Path, tmp_path: Path) -> None:
    rows = search_catalog(library / "catalog.db", limit=3)
    csv_file = tmp_path / "tags.csv"
    csv_file.write_text(
        "sha256,title,composer,genres,familiarity\n"
        + "\n".join(
            f"{row['asset_id']},Piece {index},Composer {index},\"ragtime,jazz\",high"
            for index, row in enumerate(rows)
        )
        + "\n",
        encoding="utf-8",
    )

    result = apply_edits(library, read_csv_edits(csv_file))
    assert len(result.updated) == len(rows)
    assert result.failed == ()

    stored = read_metadata(library, rows[0]["asset_id"]).descriptive_metadata
    assert stored["title"] == "Piece 0"
    assert stored["genres"] == ["ragtime", "jazz"]
    assert stored["familiarity"] == 5


def test_csv_blank_cells_do_not_wipe_existing_values(
    library: Path, asset_id: str, tmp_path: Path
) -> None:
    """A spreadsheet exported with every column must not clear what it omits."""
    update_metadata(library, asset_id, {"composer": "Keep me"})
    csv_file = tmp_path / "tags.csv"
    csv_file.write_text(f"sha256,title,composer\n{asset_id},New Title,\n", encoding="utf-8")

    apply_edits(library, read_csv_edits(csv_file))
    stored = read_metadata(library, asset_id).descriptive_metadata
    assert stored["title"] == "New Title"
    assert stored["composer"] == "Keep me"


def test_one_bad_row_does_not_lose_the_others(library: Path, tmp_path: Path) -> None:
    rows = search_catalog(library / "catalog.db", limit=2)
    csv_file = tmp_path / "tags.csv"
    csv_file.write_text(
        "sha256,title,quality_grade\n"
        f"{rows[0]['asset_id']},Good,A\n"
        f"{rows[1]['asset_id']},Bad,Z\n"
        f"sha256:{'0' * 64},Missing,B\n",
        encoding="utf-8",
    )
    result = apply_edits(library, read_csv_edits(csv_file))
    assert len(result.updated) == 1
    assert len(result.failed) == 2
    assert read_metadata(library, rows[0]["asset_id"]).descriptive_metadata["title"] == "Good"


def test_csv_without_a_key_column_is_rejected(tmp_path: Path) -> None:
    csv_file = tmp_path / "bad.csv"
    csv_file.write_text("title,composer\nA,B\n", encoding="utf-8")
    with pytest.raises(MetadataValidationError, match="asset_id or sha256"):
        read_csv_edits(csv_file)


def test_csv_with_an_unknown_column_is_rejected_before_any_write(
    library: Path, asset_id: str, tmp_path: Path
) -> None:
    csv_file = tmp_path / "bad.csv"
    csv_file.write_text(f"sha256,rights_status\n{asset_id},verified-open\n", encoding="utf-8")
    with pytest.raises(MetadataValidationError, match="unknown column"):
        read_csv_edits(csv_file)
    assert read_metadata(library, asset_id).descriptive_metadata == {}


# ---------------------------------------------- agreement with the schema


def test_curated_fields_match_the_published_schema() -> None:
    """The writer accepts exactly what midi-asset.schema.json permits.

    Validation happens in code because the schema file lives outside the
    installed package, so a wheel install has no copy of it. This test is what
    keeps the two from drifting.
    """
    published = set(SCHEMA["properties"]["descriptive_metadata"]["properties"])
    assert set(CURATED_FIELDS) == published
    assert SCHEMA["properties"]["descriptive_metadata"]["additionalProperties"] is False


def test_written_sidecars_validate_against_the_schema(library: Path, asset_id: str) -> None:
    jsonschema = pytest.importorskip("jsonschema")
    from referencing import Registry, Resource

    schemas = Path(__file__).resolve().parents[1] / "schemas"
    registry = Registry()
    for path in schemas.glob("*.schema.json"):
        document = json.loads(path.read_text())
        resource = Resource.from_contents(document)
        registry = registry.with_resource(path.name, resource)
        if document.get("$id"):
            registry = registry.with_resource(document["$id"], resource)

    update_metadata(
        library,
        asset_id,
        {
            "title": "Schema Check",
            "composer": "A. Composer",
            "genres": ["ragtime"],
            "familiarity": "high",
            "performance_type": "SOLO_PIANO",
            "quality_grade": "B",
            "favorite": True,
            "year_composed": 1899,
        },
    )
    document = json.loads(sidecar_path(library, asset_id).read_text())
    validator = jsonschema.validators.validator_for(SCHEMA)(SCHEMA, registry=registry)
    assert list(validator.iter_errors(document)) == []


# --------------------------------------------------------------- the CLI


def _tag(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "openorchestrion.library.tagging", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_tags_a_single_asset_and_reconciles_the_catalog(
    library: Path, asset_id: str
) -> None:
    result = _tag(
        asset_id,
        "--library-root",
        str(library),
        "--title",
        "Clair de Lune",
        "--composer",
        "Claude Debussy",
        "--genre",
        "classical",
        "--favorite",
    )
    assert result.returncode == 0, result.stderr
    row = get_asset(library / "catalog.db", asset_id)
    assert row["title"] == "Clair de Lune"
    assert row["favorite"] is True
    assert row["genres"] == ["classical"]


def test_cli_rejects_an_invalid_value_without_writing(library: Path, asset_id: str) -> None:
    before = sidecar_path(library, asset_id).read_bytes()
    result = _tag(asset_id, "--library-root", str(library), "--quality-grade", "Z")
    assert result.returncode == 2
    assert "quality_grade" in result.stderr
    assert sidecar_path(library, asset_id).read_bytes() == before


def test_cli_show_reports_the_revision(library: Path, asset_id: str) -> None:
    _tag(asset_id, "--library-root", str(library), "--title", "Shown")
    result = _tag(asset_id, "--library-root", str(library), "--show", "--json")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["descriptive_metadata"]["title"] == "Shown"
    assert len(payload["revision"]) == 64


def test_cli_bulk_exits_non_zero_when_a_row_fails(library: Path, tmp_path: Path) -> None:
    rows = search_catalog(library / "catalog.db", limit=1)
    csv_file = tmp_path / "tags.csv"
    csv_file.write_text(
        f"sha256,title\n{rows[0]['asset_id']},Fine\nsha256:{'0' * 64},Missing\n",
        encoding="utf-8",
    )
    result = _tag("--library-root", str(library), "--from-csv", str(csv_file))
    assert result.returncode == 1
    assert "1 tagged, 1 skipped" in result.stdout


def test_cli_refuses_a_stale_revision(library: Path, asset_id: str) -> None:
    stale = read_metadata(library, asset_id).revision
    update_metadata(library, asset_id, {"title": "Moved on"})
    result = _tag(
        asset_id, "--library-root", str(library), "--title", "Stale", "--expect-revision", stale
    )
    assert result.returncode == 2
    assert "modified by someone else" in result.stderr
    assert read_metadata(library, asset_id).descriptive_metadata["title"] == "Moved on"


def test_set_favorite_helper_matches_the_endpoint_path(library: Path, asset_id: str) -> None:
    record = set_favorite(library, asset_id, True)
    assert record.descriptive_metadata["favorite"] is True
    assert set_favorite(library, asset_id, False).descriptive_metadata["favorite"] is False
