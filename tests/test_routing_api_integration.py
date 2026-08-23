from __future__ import annotations

from pathlib import Path

from openorchestrion.api.models import QueueReplaceRequest
from openorchestrion.api.routes import _queue_specs
from openorchestrion.api.settings import Settings
from openorchestrion.library.catalog import reindex_asset, rebuild_catalog, search_catalog
from openorchestrion.library.importer import import_paths
from openorchestrion.library.metadata import update_metadata
from openorchestrion.models import PlaybackIntent
from openorchestrion.testing.midi_fixtures import generate_suite


def _settings_with_library(tmp_path: Path) -> Settings:
    root = tmp_path / "library"
    fixtures = tmp_path / "fixtures"
    generate_suite(fixtures, long_run_minutes=1)
    assert not import_paths([fixtures], root).failed
    rebuild_catalog(root)
    return Settings(
        library_root=root,
        catalog_db=root / "catalog.db",
        history_db=root / "history.db",
        virtual_midi=True,
    )


def test_intent_queue_carries_curated_performance_type_and_routing_hints(
    tmp_path: Path,
) -> None:
    settings = _settings_with_library(tmp_path)
    asset_id = search_catalog(settings.catalog_db, limit=1)[0]["asset_id"]
    update_metadata(
        settings.library_root,
        asset_id,
        {
            "title": "Two Piano Test",
            "performance_type": "TWO_PIANO",
            # Free-text instrumentation is deliberately not a routing contract.
            "instrumentation": ["Concert Grand", "Piano"],
        },
    )
    reindex_asset(settings.catalog_db, settings.library_root, asset_id)

    intent = PlaybackIntent(
        performance_types=["TWO_PIANO"],
        device_preferences=["Yamaha USB", "Casio USB"],
        routing_preferences={"piano_a": "Yamaha USB", "piano_b": "Casio USB"},
    )
    specs = _queue_specs(
        QueueReplaceRequest(intent=intent, max_tracks=1),
        settings,
    )

    assert len(specs) == 1
    spec = specs[0]
    assert spec.asset_id == asset_id
    assert spec.performance_type == "TWO_PIANO"
    assert spec.device_preferences == ("Yamaha USB", "Casio USB")
    assert spec.routing_preferences == {
        "piano_a": "Yamaha USB",
        "piano_b": "Casio USB",
    }


def test_explicit_asset_queue_carries_performance_type_without_inventing_preferences(
    tmp_path: Path,
) -> None:
    settings = _settings_with_library(tmp_path)
    asset_id = search_catalog(settings.catalog_db, limit=1)[0]["asset_id"]
    update_metadata(
        settings.library_root,
        asset_id,
        {"title": "Solo Test", "performance_type": "SOLO_PIANO"},
    )
    reindex_asset(settings.catalog_db, settings.library_root, asset_id)

    spec = _queue_specs(QueueReplaceRequest(asset_ids=[asset_id]), settings)[0]

    assert spec.performance_type == "SOLO_PIANO"
    assert spec.device_preferences == ()
    assert dict(spec.routing_preferences) == {}


def test_untagged_asset_keeps_planner_fallback_available(tmp_path: Path) -> None:
    settings = _settings_with_library(tmp_path)
    asset_id = search_catalog(settings.catalog_db, limit=1)[0]["asset_id"]

    spec = _queue_specs(QueueReplaceRequest(asset_ids=[asset_id]), settings)[0]

    assert spec.performance_type is None
    # With no curated performance type the playback routing planner analyzes
    # the MIDI timeline and its GM program state instead of guessing here.
    assert spec.routing_plan is None
