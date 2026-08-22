from __future__ import annotations

import json
from pathlib import Path

import pytest

from openorchestrion.library.catalog import CatalogError, catalog_stats, rebuild_catalog, search_catalog


def _asset(
    root: Path,
    sha: str,
    *,
    title: str,
    composer: str,
    themes=(),
    genres=(),
    moods=(),
    familiarity="high",
    energy="medium",
) -> None:
    assets = root / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    (assets / f"{sha}.mid").write_bytes(b"MThd synthetic")
    analysis = {
        "source": f"{sha}.mid",
        "sha256": sha,
        "file_size_bytes": 14,
        "midi_type": 1,
        "ticks_per_beat": 480,
        "track_count": 2,
        "duration_seconds": 180.0,
        "tracks": [
            {
                "index": 0,
                "name": "piano",
                "event_count": 10,
                "channels": [1],
                "note_count": 4,
                "note_min": 60,
                "note_max": 72,
                "program_changes": 1,
                "end_tick": 1000,
            }
        ],
        "tempo_changes": [],
        "time_signature_changes": [],
        "channels": [1],
        "melodic_channels": [1],
        "percussion_channels": [],
        "percussion_note_count": 0,
        "note_count": 4,
        "note_min": 60,
        "note_max": 72,
        "velocity": {
            "count": 4,
            "minimum": 70,
            "maximum": 100,
            "mean": 85.0,
            "median": 85.0,
            "histogram": {"70": 1, "100": 1},
        },
        "program_uses": [
            {
                "tick": 0,
                "channel": 1,
                "program_zero_based": 0,
                "gm_program_number": 1,
                "gm_name": "Acoustic Grand Piano",
                "bank_msb": 0,
                "bank_lsb": 0,
            }
        ],
        "controllers": [],
        "sustain_used": True,
        "pitch_bend_used": False,
        "channel_aftertouch_used": False,
        "poly_aftertouch_used": False,
        "sysex_count": 0,
        "peak_simultaneous_notes": 4,
        "peak_simultaneous_notes_by_channel": {"1": 4},
        "assessment": {"general_midi": "gm-compatible-structure"},
    }
    document = {
        "schema_version": 1,
        "asset_id": f"sha256:{sha}",
        "file": {
            "original_filename": f"{title}.mid",
            "stored_filename": f"{sha}.mid",
            "sha256": sha,
            "size_bytes": 14,
        },
        "provenance": {
            "imported_at": "2026-08-22T12:00:00+00:00",
            "rights_status": "verified-open",
            "source_reference": "test",
            "source_label": "fixture",
            "license": "Public Domain",
            "attribution": None,
        },
        "deterministic_analysis": analysis,
        "descriptive_metadata": {
            "title": title,
            "composer": composer,
            "themes": list(themes),
            "genres": list(genres),
            "moods": list(moods),
            "familiarity": familiarity,
            "energy": energy,
            "performance_type": "SOLO_PIANO",
            "quality_grade": "A",
        },
        "ai_enrichment": [],
    }
    (assets / f"{sha}.json").write_text(json.dumps(document), encoding="utf-8")


def test_rebuild_and_query(tmp_path: Path) -> None:
    _asset(
        tmp_path,
        "a" * 64,
        title="Clair de Lune",
        composer="Claude Debussy",
        themes=["dinner"],
        genres=["classical"],
        moods=["relaxed"],
        energy="low",
    )
    _asset(
        tmp_path,
        "b" * 64,
        title="Maple Leaf Rag",
        composer="Scott Joplin",
        themes=["party"],
        genres=["ragtime"],
        moods=["energetic"],
        energy="high",
    )
    result = rebuild_catalog(tmp_path)
    assert result.indexed_assets == 2
    assert result.indexed_compositions == 2
    rows = search_catalog(tmp_path / "catalog.db", themes=["dinner"], max_energy=2)
    assert [row["title"] for row in rows] == ["Clair de Lune"]
    assert catalog_stats(tmp_path / "catalog.db") == {
        "assets": 2,
        "compositions": 2,
        "genres": 2,
        "moods": 2,
        "themes": 2,
    }


def test_same_work_groups_multiple_performances(tmp_path: Path) -> None:
    _asset(tmp_path, "a" * 64, title="Maple Leaf Rag", composer="Scott Joplin", genres=["ragtime"])
    _asset(tmp_path, "b" * 64, title="Maple Leaf Rag", composer="Scott Joplin", genres=["ragtime"])
    result = rebuild_catalog(tmp_path)
    assert result.indexed_assets == 2
    assert result.indexed_compositions == 1


def test_strict_rebuild_does_not_replace_good_catalog(tmp_path: Path) -> None:
    _asset(tmp_path, "a" * 64, title="Good", composer="Composer")
    rebuild_catalog(tmp_path)
    original = (tmp_path / "catalog.db").read_bytes()
    bad = tmp_path / "assets" / ("b" * 64 + ".json")
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(CatalogError):
        rebuild_catalog(tmp_path)
    assert (tmp_path / "catalog.db").read_bytes() == original


def test_skip_invalid_reports_error(tmp_path: Path) -> None:
    _asset(tmp_path, "a" * 64, title="Good", composer="Composer")
    (tmp_path / "assets" / ("b" * 64 + ".json")).write_text("{not json", encoding="utf-8")
    result = rebuild_catalog(tmp_path, strict=False)
    assert result.indexed_assets == 1
    assert result.skipped_sidecars == 1
    assert result.errors
