from __future__ import annotations

import sqlite3
from pathlib import Path

from openorchestrion.models import PlaybackIntent
from openorchestrion.stations import StationConstraints, build_station


def _catalog(tmp_path: Path) -> Path:
    path = tmp_path / "catalog.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE assets(
            asset_id TEXT PRIMARY KEY,
            composition_id TEXT,
            title TEXT,
            composer TEXT,
            artist TEXT,
            era TEXT,
            performance_type TEXT,
            quality_grade TEXT,
            familiarity INTEGER,
            energy INTEGER,
            favorite INTEGER,
            duration_seconds REAL,
            rights_status TEXT,
            peak_simultaneous_notes INTEGER,
            note_min INTEGER,
            note_max INTEGER,
            sysex_count INTEGER,
            gm_assessment TEXT,
            midi_path TEXT,
            original_filename TEXT
        );
        CREATE TABLE asset_tags(asset_id TEXT, kind TEXT, value TEXT);
        """
    )
    rows = [
        (
            "a1", "c1", "Maple Leaf Rag", "Scott Joplin", None, "ragtime",
            "SOLO_PIANO", "A", 5, 4, 1, 180, "verified-open", 12, 30, 100,
            0, "gm-compatible-structure", "a1.mid", "a1.mid",
        ),
        (
            "a1b", "c1", "Maple Leaf Rag", "Scott Joplin", None, "ragtime",
            "SOLO_PIANO", "C", 5, 4, 0, 175, "verified-open", 10, 30, 100,
            0, "gm-compatible-structure", "a1b.mid", "a1b.mid",
        ),
        (
            "a2", "c2", "The Entertainer", "Scott Joplin", None, "ragtime",
            "SOLO_PIANO", "B", 5, 4, 0, 210, "verified-open", 15, 30, 100,
            0, "gm-compatible-structure", "a2.mid", "a2.mid",
        ),
        (
            "a3", "c3", "Solace", "Scott Joplin", None, "ragtime",
            "SOLO_PIANO", "A", 3, 2, 0, 300, "verified-open", 15, 30, 100,
            0, "gm-compatible-structure", "a3.mid", "a3.mid",
        ),
        (
            "a4", "c4", "Easy Winners", "Scott Joplin", None, "ragtime",
            "SOLO_PIANO", "B", 3, 4, 0, 190, "verified-open", 15, 30, 100,
            0, "gm-compatible-structure", "a4.mid", "a4.mid",
        ),
        (
            "a5", "c5", "St Louis Blues", "W. C. Handy", None, "early jazz",
            "SOLO_PIANO", "A", 5, 3, 0, 240, "verified-open", 20, 25, 100,
            0, "gm-compatible-structure", "a5.mid", "a5.mid",
        ),
        (
            "a6", "c6", "Silent Night", "Franz Gruber", None, "romantic",
            "SOLO_PIANO", "A", 5, 1, 0, 220, "verified-open", 10, 40, 90,
            0, "gm-compatible-structure", "a6.mid", "a6.mid",
        ),
        (
            "a7", "c7", "Holiday Orchestra", "Traditional", None, "modern",
            "MULTI_INSTRUMENT", "B", 5, 3, 0, 260, "verified-open", 40, 30, 100,
            0, "gm-compatible-structure", "a7.mid", "a7.mid",
        ),
        (
            "a8", "c8", "Dinner Waltz", "Anon", None, "romantic",
            "SOLO_PIANO", "B", 3, 2, 0, 200, "personal", 10, 30, 100,
            0, "gm-compatible-structure", "a8.mid", "a8.mid",
        ),
        (
            "a9", "c9", "Frog Legs Rag", "James Scott", None, "ragtime",
            "SOLO_PIANO", "A", 4, 4, 0, 205, "verified-open", 12, 30, 100,
            0, "gm-compatible-structure", "a9.mid", "a9.mid",
        ),
    ]
    conn.executemany(
        "INSERT INTO assets VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    tags = {
        "a1": [("genre", "ragtime"), ("theme", "dinner"), ("instrumentation", "piano")],
        "a1b": [("genre", "ragtime"), ("theme", "dinner"), ("instrumentation", "piano")],
        "a2": [("genre", "ragtime"), ("instrumentation", "piano")],
        "a3": [
            ("genre", "ragtime"), ("mood", "relaxed"), ("theme", "dinner"),
            ("instrumentation", "piano"),
        ],
        "a4": [("genre", "ragtime"), ("instrumentation", "piano")],
        "a5": [("genre", "jazz"), ("theme", "dinner"), ("instrumentation", "piano")],
        "a6": [
            ("theme", "Christmas"), ("theme", "dinner"), ("mood", "relaxed"),
            ("instrumentation", "piano"),
        ],
        "a7": [("theme", "Christmas"), ("instrumentation", "orchestra")],
        "a8": [("theme", "dinner"), ("mood", "relaxed"), ("instrumentation", "piano")],
        "a9": [("genre", "ragtime"), ("instrumentation", "piano")],
    }
    for asset_id, values in tags.items():
        conn.executemany(
            "INSERT INTO asset_tags VALUES (?,?,?)",
            [(asset_id, kind, value) for kind, value in values],
        )
    conn.commit()
    conn.close()
    return path


def test_prefers_best_asset_and_keeps_composer_diversity(tmp_path: Path) -> None:
    db = _catalog(tmp_path)
    queue = build_station(
        db,
        PlaybackIntent(genres=["ragtime"], composers=["Scott Joplin"]),
        seed=1,
        max_tracks=5,
    )
    ids = [item.asset_id for item in queue.items]
    assert "a1" in ids
    assert "a1b" not in ids
    composers = [item.composer for item in queue.items]
    assert composers.count("Scott Joplin") > composers.count("James Scott")
    assert "James Scott" in composers


def test_popular_christmas_prefers_exact_theme_and_high_familiarity(tmp_path: Path) -> None:
    db = _catalog(tmp_path)
    queue = build_station(
        db,
        PlaybackIntent(themes=["Christmas"], familiarity="high"),
        seed=1,
        max_tracks=2,
    )
    assert {item.asset_id for item in queue.items} == {"a6", "a7"}
    assert all(item.match_tier == 0 for item in queue.items)


def test_dinner_honors_rights_and_device_peak_constraints(tmp_path: Path) -> None:
    db = _catalog(tmp_path)
    queue = build_station(
        db,
        PlaybackIntent(themes=["dinner"], energy="low"),
        constraints=StationConstraints(
            rights_statuses=("verified-open",),
            max_peak_simultaneous_notes=16,
        ),
        seed=3,
        max_tracks=4,
    )
    ids = [item.asset_id for item in queue.items]
    assert "a8" not in ids
    assert "a5" not in ids
    assert queue.items[0].asset_id in {"a6", "a3"}


def test_exclude_tag_is_hard_constraint(tmp_path: Path) -> None:
    db = _catalog(tmp_path)
    queue = build_station(
        db,
        PlaybackIntent(genres=["ragtime"], exclude_tags=["dinner"]),
        seed=1,
        max_tracks=10,
    )
    ids = [item.asset_id for item in queue.items]
    assert "a1" not in ids
    assert "a3" not in ids


def test_seed_is_reproducible(tmp_path: Path) -> None:
    db = _catalog(tmp_path)
    intent = PlaybackIntent()
    one = build_station(db, intent, seed=99, max_tracks=6).to_dict()
    two = build_station(db, intent, seed=99, max_tracks=6).to_dict()
    assert one == two


def test_requested_duration_relaxes_preferences_when_needed(tmp_path: Path) -> None:
    db = _catalog(tmp_path)
    queue = build_station(
        db,
        PlaybackIntent(themes=["Christmas"], duration_minutes=12),
        seed=1,
        max_tracks=10,
    )
    assert queue.total_duration_seconds >= 600
    assert queue.relaxations


def test_recent_composition_is_excluded(tmp_path: Path) -> None:
    db = _catalog(tmp_path)
    queue = build_station(
        db,
        PlaybackIntent(genres=["ragtime"]),
        constraints=StationConstraints(recent_composition_ids=("c1",)),
        seed=1,
        max_tracks=10,
    )
    assert "a1" not in [item.asset_id for item in queue.items]


def test_recent_exclusion_can_be_disabled_by_intent(tmp_path: Path) -> None:
    db = _catalog(tmp_path)
    queue = build_station(
        db,
        PlaybackIntent(genres=["ragtime"], avoid_recent_repeats=False),
        constraints=StationConstraints(recent_composition_ids=("c1",)),
        seed=1,
        max_tracks=10,
    )
    assert "a1" in [item.asset_id for item in queue.items]
