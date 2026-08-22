from __future__ import annotations

import argparse
import json
import sqlite3
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, Sequence

HISTORY_SCHEMA_VERSION = 1

EventType = Literal[
    "queued",
    "started",
    "substantially_played",
    "completed",
    "skipped",
    "failed",
]


class HistoryError(ValueError):
    pass


class HistoryVersionError(HistoryError):
    pass


@dataclass(frozen=True, slots=True)
class RecentExclusions:
    asset_ids: tuple[str, ...]
    composition_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, list[str]]:
        return {
            "asset_ids": list(self.asset_ids),
            "composition_ids": list(self.composition_ids),
        }


@dataclass(frozen=True, slots=True)
class HistorySummary:
    asset_id: str
    composition_id: str | None
    qualifying_play_count: int
    last_played_at: str | None
    total_played_seconds: float
    completed_count: int
    skipped_after_substantial_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def substantial_threshold_seconds(track_duration_seconds: float | None) -> float:
    """Return the played-time threshold used for no-repeat/history credit.

    For known durations, a play counts after 50% of the track, bounded to at
    least 15 seconds and at most 60 seconds, but never beyond the full track.
    Unknown-duration material uses a 60-second threshold.
    """

    if track_duration_seconds is None:
        return 60.0
    duration = float(track_duration_seconds)
    if duration <= 0:
        raise HistoryError("track_duration_seconds must be greater than zero")
    return min(duration, min(60.0, max(15.0, duration * 0.5)))


def _iso(value: datetime | str | None = None) -> str:
    if value is None:
        value = datetime.now(timezone.utc)
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise HistoryError("timestamps must include a timezone")
        value = parsed
    if value.tzinfo is None:
        raise HistoryError("timestamps must include a timezone")
    return value.astimezone(timezone.utc).isoformat()


def _connect(path: str | Path) -> sqlite3.Connection:
    db = Path(path)
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def _initialize_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS history_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS play_attempts (
            play_id TEXT PRIMARY KEY,
            asset_id TEXT NOT NULL,
            composition_id TEXT,
            track_duration_seconds REAL,
            queued_at TEXT NOT NULL,
            started_at TEXT,
            substantially_played_at TEXT,
            ended_at TEXT,
            final_status TEXT CHECK (
                final_status IS NULL OR final_status IN ('completed','skipped','failed')
            ),
            played_seconds REAL NOT NULL DEFAULT 0 CHECK (played_seconds >= 0),
            error TEXT
        );

        CREATE TABLE IF NOT EXISTS play_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            play_id TEXT NOT NULL REFERENCES play_attempts(play_id) ON DELETE CASCADE,
            event_type TEXT NOT NULL CHECK (
                event_type IN (
                    'queued','started','substantially_played','completed','skipped','failed'
                )
            ),
            occurred_at TEXT NOT NULL,
            position_seconds REAL,
            detail TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_play_attempts_asset
            ON play_attempts(asset_id, substantially_played_at);
        CREATE INDEX IF NOT EXISTS idx_play_attempts_composition
            ON play_attempts(composition_id, substantially_played_at);
        CREATE INDEX IF NOT EXISTS idx_play_events_play
            ON play_events(play_id, event_id);
        """
    )
    version = conn.execute(
        "SELECT value FROM history_meta WHERE key='schema_version'"
    ).fetchone()
    if version is None:
        conn.execute(
            "INSERT INTO history_meta(key, value) VALUES ('schema_version', ?)",
            (str(HISTORY_SCHEMA_VERSION),),
        )
    elif int(version["value"]) != HISTORY_SCHEMA_VERSION:
        raise HistoryVersionError(
            f"unsupported history schema version {version['value']}; "
            f"expected {HISTORY_SCHEMA_VERSION}"
        )


def initialize_history(db_path: str | Path) -> None:
    with _connect(db_path) as conn:
        _initialize_schema(conn)
        conn.commit()


def _open(db_path: str | Path) -> sqlite3.Connection:
    conn = _connect(db_path)
    _initialize_schema(conn)
    return conn


def _append_event(
    conn: sqlite3.Connection,
    play_id: str,
    event_type: EventType,
    occurred_at: str,
    *,
    position_seconds: float | None = None,
    detail: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO play_events(play_id, event_type, occurred_at, position_seconds, detail)
        VALUES (?, ?, ?, ?, ?)
        """,
        (play_id, event_type, occurred_at, position_seconds, detail),
    )


def _attempt(conn: sqlite3.Connection, play_id: str) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM play_attempts WHERE play_id=?", (play_id,)
    ).fetchone()
    if row is None:
        raise HistoryError(f"unknown play_id {play_id}")
    return row


def queue_play(
    db_path: str | Path,
    *,
    asset_id: str,
    composition_id: str | None = None,
    track_duration_seconds: float | None = None,
    occurred_at: datetime | str | None = None,
    play_id: str | None = None,
) -> str:
    if not asset_id.strip():
        raise HistoryError("asset_id is required")
    if track_duration_seconds is not None and track_duration_seconds <= 0:
        raise HistoryError("track_duration_seconds must be greater than zero")
    play_id = play_id or uuid.uuid4().hex
    timestamp = _iso(occurred_at)
    with _open(db_path) as conn:
        conn.execute(
            """
            INSERT INTO play_attempts(
                play_id, asset_id, composition_id, track_duration_seconds, queued_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (play_id, asset_id, composition_id, track_duration_seconds, timestamp),
        )
        _append_event(conn, play_id, "queued", timestamp)
        conn.commit()
    return play_id


def mark_started(
    db_path: str | Path,
    play_id: str,
    *,
    occurred_at: datetime | str | None = None,
) -> None:
    timestamp = _iso(occurred_at)
    with _open(db_path) as conn:
        row = _attempt(conn, play_id)
        if row["final_status"] is not None:
            raise HistoryError("cannot start a terminal play")
        if row["started_at"] is not None:
            return
        conn.execute(
            "UPDATE play_attempts SET started_at=? WHERE play_id=?",
            (timestamp, play_id),
        )
        _append_event(conn, play_id, "started", timestamp)
        conn.commit()


def _maybe_mark_substantial(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    *,
    occurred_at: str,
    played_seconds: float,
) -> bool:
    if row["substantially_played_at"] is not None:
        return False
    threshold = substantial_threshold_seconds(row["track_duration_seconds"])
    if played_seconds + 1e-9 < threshold:
        return False
    conn.execute(
        "UPDATE play_attempts SET substantially_played_at=? WHERE play_id=?",
        (occurred_at, row["play_id"]),
    )
    _append_event(
        conn,
        row["play_id"],
        "substantially_played",
        occurred_at,
        position_seconds=played_seconds,
        detail=json.dumps({"threshold_seconds": threshold}, sort_keys=True),
    )
    return True


def update_progress(
    db_path: str | Path,
    play_id: str,
    played_seconds: float,
    *,
    occurred_at: datetime | str | None = None,
) -> bool:
    """Update progress without writing high-frequency progress events.

    Returns True only when this call crosses the substantial-listen threshold.
    """

    if played_seconds < 0:
        raise HistoryError("played_seconds must be non-negative")
    timestamp = _iso(occurred_at)
    with _open(db_path) as conn:
        row = _attempt(conn, play_id)
        if row["started_at"] is None:
            raise HistoryError("play must be started before progress is recorded")
        if row["final_status"] is not None:
            raise HistoryError("cannot update a terminal play")
        new_value = max(float(row["played_seconds"]), float(played_seconds))
        conn.execute(
            "UPDATE play_attempts SET played_seconds=? WHERE play_id=?",
            (new_value, play_id),
        )
        row = _attempt(conn, play_id)
        substantial = _maybe_mark_substantial(
            conn, row, occurred_at=timestamp, played_seconds=new_value
        )
        conn.commit()
        return substantial


def _finish(
    db_path: str | Path,
    play_id: str,
    status: Literal["completed", "skipped", "failed"],
    *,
    occurred_at: datetime | str | None = None,
    played_seconds: float | None = None,
    error: str | None = None,
) -> None:
    timestamp = _iso(occurred_at)
    with _open(db_path) as conn:
        row = _attempt(conn, play_id)
        if row["final_status"] is not None:
            if row["final_status"] == status:
                return
            raise HistoryError(
                f"play already terminal with status {row['final_status']}"
            )
        if status == "completed" and row["started_at"] is None:
            raise HistoryError("cannot complete a play that was never started")

        current = float(row["played_seconds"])
        if played_seconds is not None:
            if played_seconds < 0:
                raise HistoryError("played_seconds must be non-negative")
            current = max(current, float(played_seconds))
        if status == "completed" and row["track_duration_seconds"] is not None:
            current = max(current, float(row["track_duration_seconds"]))

        if status == "completed" and row["substantially_played_at"] is None:
            conn.execute(
                "UPDATE play_attempts SET substantially_played_at=? WHERE play_id=?",
                (timestamp, play_id),
            )
            _append_event(
                conn,
                play_id,
                "substantially_played",
                timestamp,
                position_seconds=current,
                detail=json.dumps(
                    {
                        "threshold_seconds": substantial_threshold_seconds(
                            row["track_duration_seconds"]
                        ),
                        "implied_by_completion": True,
                    },
                    sort_keys=True,
                ),
            )
        elif row["started_at"] is not None:
            _maybe_mark_substantial(
                conn, row, occurred_at=timestamp, played_seconds=current
            )

        conn.execute(
            """
            UPDATE play_attempts
            SET played_seconds=?, ended_at=?, final_status=?, error=?
            WHERE play_id=?
            """,
            (current, timestamp, status, error, play_id),
        )
        _append_event(
            conn,
            play_id,
            status,
            timestamp,
            position_seconds=current,
            detail=error,
        )
        conn.commit()


def mark_completed(
    db_path: str | Path,
    play_id: str,
    *,
    occurred_at: datetime | str | None = None,
    played_seconds: float | None = None,
) -> None:
    _finish(
        db_path,
        play_id,
        "completed",
        occurred_at=occurred_at,
        played_seconds=played_seconds,
    )


def mark_skipped(
    db_path: str | Path,
    play_id: str,
    *,
    occurred_at: datetime | str | None = None,
    played_seconds: float | None = None,
) -> None:
    _finish(
        db_path,
        play_id,
        "skipped",
        occurred_at=occurred_at,
        played_seconds=played_seconds,
    )


def mark_failed(
    db_path: str | Path,
    play_id: str,
    *,
    occurred_at: datetime | str | None = None,
    played_seconds: float | None = None,
    error: str | None = None,
) -> None:
    _finish(
        db_path,
        play_id,
        "failed",
        occurred_at=occurred_at,
        played_seconds=played_seconds,
        error=error,
    )


def recent_exclusions(
    db_path: str | Path,
    *,
    days: int,
    now: datetime | str | None = None,
) -> RecentExclusions:
    if days < 0:
        raise HistoryError("days must be non-negative")
    now_dt = datetime.fromisoformat(_iso(now))
    cutoff = (now_dt - timedelta(days=days)).isoformat()
    with _open(db_path) as conn:
        rows = conn.execute(
            """
            SELECT asset_id, composition_id
            FROM play_attempts
            WHERE substantially_played_at IS NOT NULL
              AND substantially_played_at >= ?
            """,
            (cutoff,),
        ).fetchall()
    assets = sorted({row["asset_id"] for row in rows})
    compositions = sorted(
        {row["composition_id"] for row in rows if row["composition_id"]}
    )
    return RecentExclusions(tuple(assets), tuple(compositions))


def history_summaries(
    db_path: str | Path,
    *,
    asset_ids: Sequence[str] = (),
) -> list[HistorySummary]:
    clauses = ["substantially_played_at IS NOT NULL"]
    params: list[Any] = []
    if asset_ids:
        placeholders = ",".join("?" for _ in asset_ids)
        clauses.append(f"asset_id IN ({placeholders})")
        params.extend(asset_ids)
    sql = f"""
        SELECT asset_id,
               MAX(composition_id) AS composition_id,
               COUNT(*) AS qualifying_play_count,
               MAX(substantially_played_at) AS last_played_at,
               SUM(played_seconds) AS total_played_seconds,
               SUM(CASE WHEN final_status='completed' THEN 1 ELSE 0 END) AS completed_count,
               SUM(CASE WHEN final_status='skipped' THEN 1 ELSE 0 END)
                   AS skipped_after_substantial_count
        FROM play_attempts
        WHERE {' AND '.join(clauses)}
        GROUP BY asset_id
        ORDER BY last_played_at ASC, asset_id
    """
    with _open(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [
        HistorySummary(
            asset_id=row["asset_id"],
            composition_id=row["composition_id"],
            qualifying_play_count=row["qualifying_play_count"],
            last_played_at=row["last_played_at"],
            total_played_seconds=float(row["total_played_seconds"] or 0.0),
            completed_count=row["completed_count"],
            skipped_after_substantial_count=row[
                "skipped_after_substantial_count"
            ],
        )
        for row in rows
    ]


def rank_by_staleness(
    db_path: str | Path,
    asset_ids: Sequence[str],
) -> list[str]:
    summaries = {
        summary.asset_id: summary
        for summary in history_summaries(db_path, asset_ids=asset_ids)
    }
    return sorted(
        asset_ids,
        key=lambda asset_id: (
            0 if asset_id not in summaries else 1,
            summaries[asset_id].last_played_at if asset_id in summaries else "",
            summaries[asset_id].qualifying_play_count if asset_id in summaries else 0,
            asset_id,
        ),
    )


def apply_no_repeat_window(
    constraints: Any,
    db_path: str | Path,
    *,
    days: int,
    now: datetime | str | None = None,
) -> Any:
    """Return StationConstraints with history-derived recent exclusions merged in."""

    recent = recent_exclusions(db_path, days=days, now=now)
    return replace(
        constraints,
        recent_asset_ids=tuple(
            sorted(set(constraints.recent_asset_ids).union(recent.asset_ids))
        ),
        recent_composition_ids=tuple(
            sorted(
                set(constraints.recent_composition_ids).union(
                    recent.composition_ids
                )
            )
        ),
    )


def _attempt_dict(db_path: str | Path, play_id: str) -> dict[str, Any]:
    with _open(db_path) as conn:
        return dict(_attempt(conn, play_id))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="OpenOrchestrion durable play-history utility."
    )
    parser.add_argument("db", nargs="?", default="var/history.db")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init")

    queued = sub.add_parser("queue")
    queued.add_argument("--asset-id", required=True)
    queued.add_argument("--composition-id")
    queued.add_argument("--duration", type=float)

    started = sub.add_parser("start")
    started.add_argument("play_id")

    progress = sub.add_parser("progress")
    progress.add_argument("play_id")
    progress.add_argument("seconds", type=float)

    for name in ("complete", "skip"):
        command = sub.add_parser(name)
        command.add_argument("play_id")
        command.add_argument("--seconds", type=float)

    failed = sub.add_parser("fail")
    failed.add_argument("play_id")
    failed.add_argument("--seconds", type=float)
    failed.add_argument("--error")

    recent = sub.add_parser("recent")
    recent.add_argument("--days", type=int, default=30)

    sub.add_parser("summary")

    args = parser.parse_args()

    if args.command == "init":
        initialize_history(args.db)
        print(args.db)
    elif args.command == "queue":
        print(
            queue_play(
                args.db,
                asset_id=args.asset_id,
                composition_id=args.composition_id,
                track_duration_seconds=args.duration,
            )
        )
    elif args.command == "start":
        mark_started(args.db, args.play_id)
        print(json.dumps(_attempt_dict(args.db, args.play_id), indent=2, sort_keys=True))
    elif args.command == "progress":
        substantial = update_progress(args.db, args.play_id, args.seconds)
        data = _attempt_dict(args.db, args.play_id)
        data["crossed_substantial_threshold"] = substantial
        print(json.dumps(data, indent=2, sort_keys=True))
    elif args.command == "complete":
        mark_completed(args.db, args.play_id, played_seconds=args.seconds)
        print(json.dumps(_attempt_dict(args.db, args.play_id), indent=2, sort_keys=True))
    elif args.command == "skip":
        mark_skipped(args.db, args.play_id, played_seconds=args.seconds)
        print(json.dumps(_attempt_dict(args.db, args.play_id), indent=2, sort_keys=True))
    elif args.command == "fail":
        mark_failed(
            args.db,
            args.play_id,
            played_seconds=args.seconds,
            error=args.error,
        )
        print(json.dumps(_attempt_dict(args.db, args.play_id), indent=2, sort_keys=True))
    elif args.command == "recent":
        print(
            json.dumps(
                recent_exclusions(args.db, days=args.days).to_dict(),
                indent=2,
                sort_keys=True,
            )
        )
    elif args.command == "summary":
        print(
            json.dumps(
                [item.to_dict() for item in history_summaries(args.db)],
                indent=2,
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
