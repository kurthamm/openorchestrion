from __future__ import annotations

from pathlib import Path

import pytest

from openorchestrion.library.catalog import catalog_facets, rebuild_catalog
from openorchestrion.library.importer import import_paths
from openorchestrion.library.metadata import update_metadata
from openorchestrion.testing.midi_fixtures import generate_suite


def test_facets_count_curated_values_most_common_first(tmp_path: Path) -> None:
    fixtures = tmp_path / "fixtures"
    generate_suite(fixtures, long_run_minutes=1)
    root = tmp_path / "library"
    result = import_paths([fixtures], root)
    assert not result.failed
    ids = [record.asset_id for record in result.imported]
    assert len(ids) >= 3
    update_metadata(root, ids[0], {"genres": ["baroque", "fugue"], "era": "baroque", "composer": "J. S. Bach", "themes": ["study"]})
    update_metadata(root, ids[1], {"genres": ["baroque"], "era": "baroque", "composer": "J. S. Bach", "moods": ["calm"]})
    update_metadata(root, ids[2], {"genres": ["ragtime"], "era": "romantic", "composer": "Scott Joplin", "moods": ["playful"]})
    rebuild_catalog(root)

    facets = catalog_facets(root / "catalog.db")
    assert facets["genres"][0] == {"value": "baroque", "count": 2}
    assert {e["value"] for e in facets["genres"]} == {"baroque", "fugue", "ragtime"}
    assert facets["eras"][0] == {"value": "baroque", "count": 2}
    assert facets["composers"][0] == {"value": "J. S. Bach", "count": 2}
    assert facets["themes"] == [{"value": "study", "count": 1}]
    assert {e["value"] for e in facets["moods"]} == {"calm", "playful"}
    assert len(catalog_facets(root / "catalog.db", limit=1)["genres"]) == 1
    with pytest.raises(ValueError):
        catalog_facets(root / "catalog.db", limit=0)
