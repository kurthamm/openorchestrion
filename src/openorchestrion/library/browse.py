"""Read-only listening-room queries; the admitted catalog remains authoritative."""

from __future__ import annotations

import unicodedata
from copy import deepcopy
from functools import lru_cache
from threading import Lock
from contextlib import closing
from pathlib import Path
from typing import Any

from .catalog import _connect
from .title_identity import IDENTITY_FIELDS


@lru_cache(maxsize=32768)
def _fold(value: str | None) -> str:
    return "".join(
        c
        for c in unicodedata.normalize("NFKD", value or "").casefold()
        if not unicodedata.combining(c)
    )


def browse(
    db: Path,
    *,
    text: str = "",
    genre: str = "",
    mood: str = "",
    era: str = "",
    composer: str = "",
    source: str = "",
    arrangement: str = "",
    favorite: bool = False,
    sort: str = "title",
    offset: int = 0,
    limit: int = 40,
) -> dict[str, Any]:
    orders = {
        "title": "fold(title)",
        "composer": "composer COLLATE NOCASE, title COLLATE NOCASE",
        "duration": "duration_seconds, title COLLATE NOCASE",
        "newest": "imported_at DESC, title COLLATE NOCASE",
    }
    if sort not in orders or offset < 0 or not 1 <= limit <= 100:
        raise ValueError("Invalid browse pagination or sort")
    clauses, args = [], []
    for word in _fold(text).split():
        clauses.append(
            "instr(fold(coalesce(title,'') || ' ' || coalesce(composer,'') || ' ' || coalesce(artist,'') || ' ' || original_filename), ?) > 0"
        )
        clauses[-1] = "(" + clauses[-1] + " OR EXISTS (SELECT 1 FROM asset_tags t WHERE t.asset_id=a.asset_id AND t.kind IN ('identity_source_title','identity_source_context') AND instr(fold(t.value), ?) > 0))"
        args.extend([word, word])
    for column, value in [
        ("era", era),
        ("composer", composer),
        ("source_label", source),
        ("performance_type", arrangement),
    ]:
        if value:
            clauses.append(f"{column} = ? COLLATE NOCASE")
            args.append(value)
    for kind, value in [("genre", genre), ("mood", mood)]:
        if value:
            clauses.append(
                "EXISTS (SELECT 1 FROM asset_tags t WHERE t.asset_id=a.asset_id AND t.kind=? AND t.value=? COLLATE NOCASE)"
            )
            args.extend([kind, value])
    if favorite:
        clauses.append("favorite=1")
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with closing(_connect(db)) as conn:
        conn.create_function("fold", 1, _fold, deterministic=True)
        conn.execute("BEGIN")  # count and page describe the same snapshot
        total = conn.execute("SELECT count(*) FROM assets a" + where, args).fetchone()[0]
        identity_columns = ",".join(
            f"(SELECT value FROM asset_tags t WHERE t.asset_id=a.asset_id AND t.kind='identity_{field}' LIMIT 1) AS {field}"
            for field in IDENTITY_FIELDS
        )
        rows = conn.execute(
            "SELECT asset_id,title,composer,artist,performance_type,duration_seconds,favorite,source_label,era," + identity_columns + " FROM assets a"
            + where
            + " ORDER BY "
            + orders[sort]
            + ", asset_id LIMIT ? OFFSET ?",
            [*args, limit, offset],
        ).fetchall()
    return {
        "items": [dict(r) for r in rows],
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": offset + limit < total,
    }


_facet_lock = Lock()
_facet_cache: dict[Path, tuple[tuple, dict]] = {}


def _catalog_signature(db: Path) -> tuple:
    result = []
    # WAL writes and atomic catalog replacement must both invalidate the cache.
    for path in (db, Path(str(db) + "-wal")):
        try:
            s = path.stat()
            result.append((s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns))
        except FileNotFoundError:
            result.append(None)
    return tuple(result)


def browse_facets(db: Path) -> dict[str, Any]:
    db = db.resolve()
    with _facet_lock:
        signature = _catalog_signature(db)
        cached = _facet_cache.get(db)
        if cached is not None and cached[0] == signature:
            return deepcopy(cached[1])
        result = _read_facets(db)
        if signature == _catalog_signature(db):
            if len(_facet_cache) >= 4:
                _facet_cache.clear()
            _facet_cache[db] = (signature, result)
        return deepcopy(result)


def _read_facets(db: Path) -> dict[str, Any]:
    with closing(_connect(db)) as conn:
        conn.execute("BEGIN")
        result = {}
        for key, column in [
            ("eras", "era"),
            ("composers", "composer"),
            ("sources", "source_label"),
            ("arrangements", "performance_type"),
        ]:
            result[key] = [
                dict(r)
                for r in conn.execute(
                    f"SELECT {column} AS value, count(*) AS count FROM assets WHERE {column} IS NOT NULL AND {column} <> '' GROUP BY {column} COLLATE NOCASE ORDER BY {column} COLLATE NOCASE"
                )
            ]
        for key, kind in [("genres", "genre"), ("moods", "mood")]:
            result[key] = [
                dict(r)
                for r in conn.execute(
                    "SELECT value,count(*) AS count FROM asset_tags WHERE kind=? GROUP BY value COLLATE NOCASE ORDER BY value COLLATE NOCASE",
                    [kind],
                )
            ]
        result["total"] = conn.execute("SELECT count(*) FROM assets").fetchone()[0]
        result["favorites"] = conn.execute(
            "SELECT count(*) FROM assets WHERE favorite=1"
        ).fetchone()[0]
    return result


def performance_detail(db: Path, asset_id: str) -> dict[str, Any] | None:
    with closing(_connect(db)) as conn:
        row = conn.execute(
            "SELECT source_label,source_reference,license,attribution,rights_status,midi_type,ticks_per_beat,track_count,note_count,note_min,note_max,velocity_min,velocity_max,sustain_used,pitch_bend_used,sysex_count,peak_simultaneous_notes,gm_assessment FROM assets WHERE asset_id=?",
            [asset_id],
        ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["instruments"] = [
            dict(r)
            for r in conn.execute(
                "SELECT channel,gm_program_number,gm_name,bank_msb,bank_lsb,min(tick) AS first_tick,count(*) AS changes FROM asset_programs WHERE asset_id=? GROUP BY channel,gm_program_number,gm_name,bank_msb,bank_lsb ORDER BY channel,first_tick",
                [asset_id],
            )
        ]
        result["channels"] = [
            dict(r)
            for r in conn.execute(
                "SELECT channel,is_percussion FROM asset_channels WHERE asset_id=? ORDER BY channel",
                [asset_id],
            )
        ]
    return result
