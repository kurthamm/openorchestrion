from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from openorchestrion.history import (
    HistoryVersionError,
    apply_no_repeat_window,
    history_summaries,
    initialize_history,
    mark_completed,
    mark_failed,
    mark_skipped,
    mark_started,
    queue_play,
    rank_by_staleness,
    recent_exclusions,
    substantial_threshold_seconds,
    update_progress,
)
from openorchestrion.stations import StationConstraints


NOW = datetime(2026, 8, 22, 14, 0, tzinfo=timezone.utc)


def test_queued_and_short_skip_do_not_count_as_played(tmp_path) -> None:
    db = tmp_path / "history.db"
    play_id = queue_play(
        db,
        asset_id="asset-a",
        composition_id="composition-a",
        track_duration_seconds=180,
        occurred_at=NOW,
    )
    assert recent_exclusions(db, days=30, now=NOW + timedelta(hours=1)).asset_ids == ()

    mark_started(db, play_id, occurred_at=NOW + timedelta(seconds=1))
    mark_skipped(
        db,
        play_id,
        played_seconds=10,
        occurred_at=NOW + timedelta(seconds=11),
    )
    assert recent_exclusions(db, days=30, now=NOW + timedelta(hours=1)).asset_ids == ()


def test_progress_crosses_substantial_threshold_once(tmp_path) -> None:
    db = tmp_path / "history.db"
    play_id = queue_play(
        db,
        asset_id="asset-a",
        composition_id="composition-a",
        track_duration_seconds=120,
        occurred_at=NOW,
    )
    mark_started(db, play_id, occurred_at=NOW + timedelta(seconds=1))

    assert substantial_threshold_seconds(120) == 60
    assert update_progress(
        db, play_id, 59, occurred_at=NOW + timedelta(seconds=60)
    ) is False
    assert update_progress(
        db, play_id, 60, occurred_at=NOW + timedelta(seconds=61)
    ) is True
    assert update_progress(
        db, play_id, 90, occurred_at=NOW + timedelta(seconds=91)
    ) is False

    recent = recent_exclusions(db, days=30, now=NOW + timedelta(hours=1))
    assert recent.asset_ids == ("asset-a",)
    assert recent.composition_ids == ("composition-a",)

    with sqlite3.connect(db) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM play_events WHERE event_type='substantially_played'"
        ).fetchone()[0]
    assert count == 1


def test_completed_short_track_always_counts(tmp_path) -> None:
    db = tmp_path / "history.db"
    play_id = queue_play(
        db,
        asset_id="short",
        composition_id="short-composition",
        track_duration_seconds=10,
        occurred_at=NOW,
    )
    assert substantial_threshold_seconds(10) == 10
    mark_started(db, play_id, occurred_at=NOW + timedelta(seconds=1))
    mark_completed(db, play_id, occurred_at=NOW + timedelta(seconds=11))

    recent = recent_exclusions(db, days=30, now=NOW + timedelta(hours=1))
    assert recent.asset_ids == ("short",)


def test_skipped_after_substantial_counts_but_early_failure_does_not(tmp_path) -> None:
    db = tmp_path / "history.db"

    skipped = queue_play(
        db,
        asset_id="skipped-late",
        composition_id="c1",
        track_duration_seconds=300,
        occurred_at=NOW,
    )
    mark_started(db, skipped, occurred_at=NOW + timedelta(seconds=1))
    mark_skipped(
        db,
        skipped,
        played_seconds=75,
        occurred_at=NOW + timedelta(seconds=76),
    )

    failed = queue_play(
        db,
        asset_id="failed-early",
        composition_id="c2",
        track_duration_seconds=300,
        occurred_at=NOW,
    )
    mark_started(db, failed, occurred_at=NOW + timedelta(seconds=1))
    mark_failed(
        db,
        failed,
        played_seconds=5,
        error="device disconnected",
        occurred_at=NOW + timedelta(seconds=6),
    )

    recent = recent_exclusions(db, days=30, now=NOW + timedelta(hours=1))
    assert "skipped-late" in recent.asset_ids
    assert "failed-early" not in recent.asset_ids


def test_history_summary_and_staleness(tmp_path) -> None:
    db = tmp_path / "history.db"
    older = queue_play(
        db,
        asset_id="older",
        track_duration_seconds=100,
        occurred_at=NOW - timedelta(days=20),
    )
    mark_started(db, older, occurred_at=NOW - timedelta(days=20) + timedelta(seconds=1))
    mark_completed(db, older, occurred_at=NOW - timedelta(days=20) + timedelta(seconds=100))

    newer = queue_play(
        db,
        asset_id="newer",
        track_duration_seconds=100,
        occurred_at=NOW - timedelta(days=2),
    )
    mark_started(db, newer, occurred_at=NOW - timedelta(days=2) + timedelta(seconds=1))
    mark_completed(db, newer, occurred_at=NOW - timedelta(days=2) + timedelta(seconds=100))

    summaries = {item.asset_id: item for item in history_summaries(db)}
    assert summaries["older"].qualifying_play_count == 1
    assert summaries["older"].completed_count == 1
    assert rank_by_staleness(db, ["newer", "never", "older"]) == [
        "never",
        "older",
        "newer",
    ]


def test_apply_no_repeat_window_merges_existing_constraints(tmp_path) -> None:
    db = tmp_path / "history.db"
    play_id = queue_play(
        db,
        asset_id="recent-asset",
        composition_id="recent-composition",
        track_duration_seconds=60,
        occurred_at=NOW,
    )
    mark_started(db, play_id, occurred_at=NOW + timedelta(seconds=1))
    mark_completed(db, play_id, occurred_at=NOW + timedelta(seconds=60))

    constraints = StationConstraints(
        recent_asset_ids=("already-excluded",),
        recent_composition_ids=("already-excluded-composition",),
    )
    merged = apply_no_repeat_window(
        constraints,
        db,
        days=30,
        now=NOW + timedelta(hours=1),
    )
    assert set(merged.recent_asset_ids) == {"already-excluded", "recent-asset"}
    assert set(merged.recent_composition_ids) == {
        "already-excluded-composition",
        "recent-composition",
    }


def test_history_schema_version_is_checked(tmp_path) -> None:
    db = tmp_path / "history.db"
    initialize_history(db)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE history_meta SET value='99' WHERE key='schema_version'"
        )
        conn.commit()

    with pytest.raises(HistoryVersionError):
        recent_exclusions(db, days=30, now=NOW)
