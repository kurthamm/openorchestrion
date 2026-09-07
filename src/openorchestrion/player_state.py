"""Durable saved collections and recoverable player-session state."""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

SCHEMA_VERSION = 1
CollectionKind = Literal["playlist", "station"]


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_info (
            version INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS collections (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL COLLATE NOCASE UNIQUE,
            kind TEXT NOT NULL CHECK (kind IN ('playlist', 'station')),
            intent_json TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS collection_items (
            collection_id TEXT NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
            position INTEGER NOT NULL,
            asset_id TEXT NOT NULL,
            PRIMARY KEY (collection_id, position)
        );
        CREATE TABLE IF NOT EXISTS player_session (
            singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
            state_json TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS song_preferences (
            asset_id TEXT PRIMARY KEY,
            tempo_percent INTEGER NOT NULL DEFAULT 100 CHECK (tempo_percent BETWEEN 50 AND 200),
            volume_percent INTEGER NOT NULL DEFAULT 100 CHECK (volume_percent BETWEEN 0 AND 150),
            rendering_json TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    row = connection.execute("SELECT version FROM schema_info").fetchone()
    if row is None:
        connection.execute("INSERT INTO schema_info(version) VALUES (?)", (SCHEMA_VERSION,))
    elif row["version"] != SCHEMA_VERSION:
        connection.close()
        raise RuntimeError(f"unsupported player state schema {row['version']}")
    connection.commit()
    return connection


@dataclass(frozen=True, slots=True)
class SavedCollection:
    id: str
    name: str
    kind: CollectionKind
    asset_ids: tuple[str, ...]
    intent: dict[str, Any] | None
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "asset_ids": list(self.asset_ids),
            "intent": self.intent,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class PlayerStateStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    @staticmethod
    def _collection(connection: sqlite3.Connection, row: sqlite3.Row) -> SavedCollection:
        assets = connection.execute(
            "SELECT asset_id FROM collection_items WHERE collection_id=? ORDER BY position",
            (row["id"],),
        ).fetchall()
        return SavedCollection(
            id=row["id"],
            name=row["name"],
            kind=row["kind"],
            asset_ids=tuple(item["asset_id"] for item in assets),
            intent=json.loads(row["intent_json"]) if row["intent_json"] else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def list_collections(self) -> list[SavedCollection]:
        with _connect(self.path) as connection:
            rows = connection.execute("SELECT * FROM collections ORDER BY name COLLATE NOCASE").fetchall()
            return [self._collection(connection, row) for row in rows]

    def get_collection(self, collection_id: str) -> SavedCollection | None:
        with _connect(self.path) as connection:
            row = connection.execute("SELECT * FROM collections WHERE id=?", (collection_id,)).fetchone()
            return self._collection(connection, row) if row else None

    def save_collection(
        self,
        *,
        name: str,
        kind: CollectionKind,
        asset_ids: list[str] | tuple[str, ...] = (),
        intent: dict[str, Any] | None = None,
        collection_id: str | None = None,
    ) -> SavedCollection:
        cleaned = " ".join(name.split())
        if not cleaned or len(cleaned) > 100:
            raise ValueError("name must contain 1..100 characters")
        if kind == "playlist" and not asset_ids:
            raise ValueError("a playlist requires at least one asset")
        if kind == "station" and intent is None:
            raise ValueError("a station requires an intent")
        identifier = collection_id or str(uuid.uuid4())
        with _connect(self.path) as connection:
            connection.execute(
                """INSERT INTO collections(id,name,kind,intent_json) VALUES (?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name, kind=excluded.kind,
                intent_json=excluded.intent_json, updated_at=CURRENT_TIMESTAMP""",
                (identifier, cleaned, kind, json.dumps(intent, sort_keys=True) if intent else None),
            )
            connection.execute("DELETE FROM collection_items WHERE collection_id=?", (identifier,))
            connection.executemany(
                "INSERT INTO collection_items(collection_id,position,asset_id) VALUES (?,?,?)",
                ((identifier, index, asset) for index, asset in enumerate(asset_ids)),
            )
            row = connection.execute("SELECT * FROM collections WHERE id=?", (identifier,)).fetchone()
            assert row is not None
            return self._collection(connection, row)

    def rename_collection(self, collection_id: str, name: str) -> SavedCollection | None:
        cleaned = " ".join(name.split())
        if not cleaned or len(cleaned) > 100:
            raise ValueError("name must contain 1..100 characters")
        with _connect(self.path) as connection:
            cursor = connection.execute(
                "UPDATE collections SET name=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (cleaned, collection_id),
            )
            if not cursor.rowcount:
                return None
            row = connection.execute("SELECT * FROM collections WHERE id=?", (collection_id,)).fetchone()
            assert row is not None
            return self._collection(connection, row)

    def delete_collection(self, collection_id: str) -> bool:
        with _connect(self.path) as connection:
            return bool(connection.execute("DELETE FROM collections WHERE id=?", (collection_id,)).rowcount)

    def save_session(self, state: dict[str, Any]) -> None:
        encoded = json.dumps(state, separators=(",", ":"), sort_keys=True)
        with _connect(self.path) as connection:
            connection.execute(
                """INSERT INTO player_session(singleton,state_json) VALUES (1,?)
                ON CONFLICT(singleton) DO UPDATE SET state_json=excluded.state_json,
                updated_at=CURRENT_TIMESTAMP""",
                (encoded,),
            )

    def load_session(self) -> dict[str, Any] | None:
        with _connect(self.path) as connection:
            row = connection.execute("SELECT state_json FROM player_session WHERE singleton=1").fetchone()
            return json.loads(row["state_json"]) if row else None

    def get_song_preference(self, asset_id: str) -> dict[str, Any] | None:
        with _connect(self.path) as connection:
            row = connection.execute(
                "SELECT tempo_percent,volume_percent,rendering_json,updated_at FROM song_preferences WHERE asset_id=?",
                (asset_id,),
            ).fetchone()
            if row is None:
                return None
            return {
                "asset_id": asset_id, "tempo_percent": row["tempo_percent"],
                "volume_percent": row["volume_percent"],
                "rendering": json.loads(row["rendering_json"]) if row["rendering_json"] else None,
                "updated_at": row["updated_at"],
            }

    def save_song_preference(self, asset_id: str, *, tempo_percent: int = 100,
                             volume_percent: int = 100, rendering: dict[str, Any] | None = None) -> dict[str, Any]:
        if not 50 <= tempo_percent <= 200 or not 0 <= volume_percent <= 150:
            raise ValueError("song preference is outside its supported range")
        with _connect(self.path) as connection:
            connection.execute(
                """INSERT INTO song_preferences(asset_id,tempo_percent,volume_percent,rendering_json)
                VALUES (?,?,?,?) ON CONFLICT(asset_id) DO UPDATE SET
                tempo_percent=excluded.tempo_percent, volume_percent=excluded.volume_percent,
                rendering_json=excluded.rendering_json, updated_at=CURRENT_TIMESTAMP""",
                (asset_id, tempo_percent, volume_percent, json.dumps(rendering) if rendering else None),
            )
        result = self.get_song_preference(asset_id)
        assert result is not None
        return result

    def delete_song_preference(self, asset_id: str) -> bool:
        with _connect(self.path) as connection:
            return bool(connection.execute("DELETE FROM song_preferences WHERE asset_id=?", (asset_id,)).rowcount)
