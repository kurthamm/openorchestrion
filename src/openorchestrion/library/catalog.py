from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

CATALOG_SCHEMA_VERSION = 1
TAG_FIELDS = {
    "genres": "genre",
    "moods": "mood",
    "themes": "theme",
    "tags": "tag",
    "instrumentation": "instrumentation",
}
LEVELS = {"low": 1, "medium": 3, "high": 5}


class CatalogError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RebuildResult:
    db_path: str
    indexed_assets: int
    indexed_compositions: int
    skipped_sidecars: int
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["errors"] = list(self.errors)
        return result


def _connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE catalog_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE compositions (
            composition_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            composer TEXT,
            year_composed INTEGER,
            era TEXT
        );

        CREATE TABLE assets (
            asset_id TEXT PRIMARY KEY,
            sha256 TEXT NOT NULL UNIQUE,
            composition_id TEXT REFERENCES compositions(composition_id),
            original_filename TEXT NOT NULL,
            stored_filename TEXT NOT NULL,
            size_bytes INTEGER,
            imported_at TEXT NOT NULL,
            rights_status TEXT NOT NULL,
            source_reference TEXT,
            source_label TEXT,
            license TEXT,
            attribution TEXT,
            title TEXT,
            composer TEXT,
            artist TEXT,
            era TEXT,
            year_composed INTEGER,
            performance_type TEXT,
            quality_grade TEXT,
            familiarity INTEGER,
            energy INTEGER,
            favorite INTEGER NOT NULL DEFAULT 0 CHECK (favorite IN (0, 1)),
            midi_type INTEGER NOT NULL,
            ticks_per_beat INTEGER NOT NULL,
            track_count INTEGER NOT NULL,
            duration_seconds REAL NOT NULL,
            note_count INTEGER NOT NULL,
            note_min INTEGER,
            note_max INTEGER,
            velocity_min INTEGER,
            velocity_max INTEGER,
            velocity_mean REAL,
            sustain_used INTEGER NOT NULL CHECK (sustain_used IN (0, 1)),
            pitch_bend_used INTEGER NOT NULL CHECK (pitch_bend_used IN (0, 1)),
            sysex_count INTEGER NOT NULL,
            peak_simultaneous_notes INTEGER NOT NULL,
            percussion_note_count INTEGER NOT NULL,
            gm_assessment TEXT,
            metadata_path TEXT NOT NULL,
            midi_path TEXT NOT NULL
        );

        CREATE TABLE asset_tags (
            asset_id TEXT NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE,
            kind TEXT NOT NULL,
            value TEXT NOT NULL COLLATE NOCASE,
            PRIMARY KEY (asset_id, kind, value)
        );

        CREATE TABLE asset_channels (
            asset_id TEXT NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE,
            channel INTEGER NOT NULL CHECK (channel BETWEEN 1 AND 16),
            is_percussion INTEGER NOT NULL CHECK (is_percussion IN (0, 1)),
            PRIMARY KEY (asset_id, channel)
        );

        CREATE TABLE asset_programs (
            asset_id TEXT NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE,
            sequence_index INTEGER NOT NULL,
            tick INTEGER NOT NULL,
            channel INTEGER NOT NULL,
            gm_program_number INTEGER NOT NULL,
            gm_name TEXT NOT NULL,
            bank_msb INTEGER NOT NULL,
            bank_lsb INTEGER NOT NULL,
            PRIMARY KEY (asset_id, sequence_index)
        );

        CREATE TABLE asset_tracks (
            asset_id TEXT NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE,
            track_index INTEGER NOT NULL,
            name TEXT,
            event_count INTEGER NOT NULL,
            channels_json TEXT NOT NULL,
            note_count INTEGER NOT NULL,
            note_min INTEGER,
            note_max INTEGER,
            program_changes INTEGER NOT NULL,
            end_tick INTEGER NOT NULL,
            PRIMARY KEY (asset_id, track_index)
        );

        CREATE INDEX idx_assets_title ON assets(title COLLATE NOCASE);
        CREATE INDEX idx_assets_composer ON assets(composer COLLATE NOCASE);
        CREATE INDEX idx_assets_rights ON assets(rights_status);
        CREATE INDEX idx_assets_performance_type ON assets(performance_type);
        CREATE INDEX idx_assets_familiarity ON assets(familiarity);
        CREATE INDEX idx_assets_energy ON assets(energy);
        CREATE INDEX idx_asset_tags_kind_value ON asset_tags(kind, value COLLATE NOCASE);
        CREATE INDEX idx_asset_programs_program ON asset_programs(gm_program_number);
        """
    )
    conn.execute(
        "INSERT INTO catalog_meta(key, value) VALUES (?, ?)",
        ("schema_version", str(CATALOG_SCHEMA_VERSION)),
    )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    return int(value)


def _level(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in LEVELS:
            return LEVELS[lowered]
        value = int(lowered)
    result = int(value)
    if not 1 <= result <= 5:
        raise CatalogError(f"level must be 1..5 or low/medium/high, got {value!r}")
    return result


def _list_of_strings(value: Any, field: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        raise CatalogError(f"descriptive_metadata.{field} must be a string or list")
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = _optional_str(item)
        if text is None:
            continue
        key = text.casefold()
        if key not in seen:
            result.append(text)
            seen.add(key)
    return result


def _derived_composition_id(title: str, composer: str | None) -> str:
    normalized = f"{(composer or '').strip().casefold()}\n{title.strip().casefold()}"
    digest = hashlib.sha1(normalized.encode("utf-8"), usedforsecurity=False).hexdigest()
    return f"derived:{digest}"


def _read_sidecar(path: Path, library_root: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CatalogError(f"{path}: cannot read JSON: {exc}") from exc

    if document.get("schema_version") != 1:
        raise CatalogError(f"{path}: unsupported schema_version {document.get('schema_version')!r}")

    file_info = document.get("file") or {}
    analysis = document.get("deterministic_analysis") or {}
    sha = file_info.get("sha256")
    asset_id = document.get("asset_id")
    if not isinstance(sha, str) or len(sha) != 64:
        raise CatalogError(f"{path}: invalid file.sha256")
    if asset_id != f"sha256:{sha}":
        raise CatalogError(f"{path}: asset_id does not match file.sha256")
    if analysis.get("sha256") != sha:
        raise CatalogError(f"{path}: deterministic_analysis.sha256 does not match file.sha256")
    if path.stem != sha:
        raise CatalogError(f"{path}: sidecar filename must equal SHA-256")

    stored_filename = file_info.get("stored_filename")
    expected_midi = library_root / "assets" / str(stored_filename)
    if stored_filename != f"{sha}.mid":
        raise CatalogError(f"{path}: stored_filename does not match SHA-256")
    if not expected_midi.is_file():
        raise CatalogError(f"{path}: MIDI object missing: {expected_midi}")

    return document


def _index_document(
    conn: sqlite3.Connection,
    document: dict[str, Any],
    *,
    sidecar_path: Path,
    library_root: Path,
) -> None:
    file_info = document["file"]
    provenance = document["provenance"]
    analysis = document["deterministic_analysis"]
    metadata = document.get("descriptive_metadata") or {}
    if not isinstance(metadata, dict):
        raise CatalogError(f"{sidecar_path}: descriptive_metadata must be an object")

    title = _optional_str(metadata.get("title") or metadata.get("composition_title"))
    composer = _optional_str(metadata.get("composer"))
    artist = _optional_str(metadata.get("artist"))
    era = _optional_str(metadata.get("era"))
    year_composed = _optional_int(metadata.get("year_composed"))
    performance_type = _optional_str(metadata.get("performance_type"))
    quality_grade = _optional_str(metadata.get("quality_grade"))
    familiarity = _level(metadata.get("familiarity"))
    energy = _level(metadata.get("energy"))
    favorite = 1 if bool(metadata.get("favorite", False)) else 0

    composition_id = _optional_str(metadata.get("composition_id"))
    if composition_id is None and title is not None:
        composition_id = _derived_composition_id(title, composer)
    if composition_id is not None:
        if title is None:
            raise CatalogError(f"{sidecar_path}: composition_id requires a title")
        conn.execute(
            """
            INSERT INTO compositions(composition_id, title, composer, year_composed, era)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(composition_id) DO UPDATE SET
                title=excluded.title,
                composer=COALESCE(excluded.composer, compositions.composer),
                year_composed=COALESCE(excluded.year_composed, compositions.year_composed),
                era=COALESCE(excluded.era, compositions.era)
            """,
            (composition_id, title, composer, year_composed, era),
        )

    velocity = analysis.get("velocity") or {}
    assessment = analysis.get("assessment") or {}
    gm_assessment = _optional_str(
        assessment.get("general_midi")
        or assessment.get("gm_assessment")
        or assessment.get("general_midi_assessment")
    )
    sha = file_info["sha256"]
    midi_path = library_root / "assets" / file_info["stored_filename"]

    conn.execute(
        """
        INSERT INTO assets(
            asset_id, sha256, composition_id, original_filename, stored_filename,
            size_bytes, imported_at, rights_status, source_reference, source_label,
            license, attribution, title, composer, artist, era, year_composed,
            performance_type, quality_grade, familiarity, energy, favorite,
            midi_type, ticks_per_beat, track_count, duration_seconds, note_count,
            note_min, note_max, velocity_min, velocity_max, velocity_mean,
            sustain_used, pitch_bend_used, sysex_count, peak_simultaneous_notes,
            percussion_note_count, gm_assessment, metadata_path, midi_path
        ) VALUES (
            ?,?,?,?,?, ?,?,?,?,?, ?,?,?,?,?, ?,?,?,?,?, ?,?,?,?,?, ?,?,?,?,?, ?,?,?,?,?, ?,?,?,?,?
        )
        """,
        (
            document["asset_id"], sha, composition_id,
            file_info["original_filename"], file_info["stored_filename"], file_info.get("size_bytes"),
            provenance["imported_at"], provenance["rights_status"], provenance.get("source_reference"),
            provenance.get("source_label"), provenance.get("license"), provenance.get("attribution"),
            title, composer, artist, era, year_composed, performance_type, quality_grade,
            familiarity, energy, favorite, analysis["midi_type"], analysis["ticks_per_beat"],
            analysis["track_count"], analysis["duration_seconds"], analysis["note_count"],
            analysis.get("note_min"), analysis.get("note_max"), velocity.get("minimum"),
            velocity.get("maximum"), velocity.get("mean"), int(bool(analysis["sustain_used"])),
            int(bool(analysis["pitch_bend_used"])), analysis["sysex_count"],
            analysis["peak_simultaneous_notes"], analysis["percussion_note_count"], gm_assessment,
            str(sidecar_path.relative_to(library_root)), str(midi_path.relative_to(library_root)),
        ),
    )

    percussion = set(analysis.get("percussion_channels") or [])
    for channel in analysis.get("channels") or []:
        conn.execute(
            "INSERT INTO asset_channels(asset_id, channel, is_percussion) VALUES (?, ?, ?)",
            (document["asset_id"], channel, int(channel in percussion)),
        )

    for index, program in enumerate(analysis.get("program_uses") or []):
        conn.execute(
            """INSERT INTO asset_programs(
                asset_id, sequence_index, tick, channel, gm_program_number, gm_name, bank_msb, bank_lsb
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                document["asset_id"], index, program["tick"], program["channel"],
                program["gm_program_number"], program["gm_name"], program["bank_msb"], program["bank_lsb"],
            ),
        )

    for track in analysis.get("tracks") or []:
        conn.execute(
            """INSERT INTO asset_tracks(
                asset_id, track_index, name, event_count, channels_json, note_count,
                note_min, note_max, program_changes, end_tick
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                document["asset_id"], track["index"], track.get("name"), track["event_count"],
                json.dumps(track.get("channels") or []), track["note_count"], track.get("note_min"),
                track.get("note_max"), track["program_changes"], track["end_tick"],
            ),
        )

    for field, kind in TAG_FIELDS.items():
        for value in _list_of_strings(metadata.get(field), field):
            conn.execute(
                "INSERT INTO asset_tags(asset_id, kind, value) VALUES (?, ?, ?)",
                (document["asset_id"], kind, value),
            )


def rebuild_catalog(
    library_root: str | Path,
    *,
    db_path: str | Path | None = None,
    strict: bool = True,
) -> RebuildResult:
    root = Path(library_root).resolve()
    assets_dir = root / "assets"
    if not assets_dir.is_dir():
        raise FileNotFoundError(assets_dir)

    destination = Path(db_path).resolve() if db_path else root / "catalog.db"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    if temporary.exists():
        temporary.unlink()

    indexed = 0
    skipped = 0
    errors: list[str] = []
    conn = _connect(temporary)
    try:
        initialize_schema(conn)
        for sidecar in sorted(assets_dir.glob("*.json")):
            try:
                document = _read_sidecar(sidecar, root)
                _index_document(conn, document, sidecar_path=sidecar, library_root=root)
                indexed += 1
            except (CatalogError, KeyError, TypeError, ValueError) as exc:
                message = str(exc)
                if strict:
                    raise CatalogError(message) from exc
                errors.append(message)
                skipped += 1
        conn.execute(
            "INSERT INTO catalog_meta(key, value) VALUES (?, ?)",
            ("asset_count", str(indexed)),
        )
        conn.commit()
        composition_count = conn.execute("SELECT COUNT(*) FROM compositions").fetchone()[0]
    except Exception:
        conn.close()
        temporary.unlink(missing_ok=True)
        raise
    else:
        conn.close()
        os.replace(temporary, destination)

    return RebuildResult(
        db_path=str(destination),
        indexed_assets=indexed,
        indexed_compositions=composition_count,
        skipped_sidecars=skipped,
        errors=tuple(errors),
    )


def search_catalog(
    db_path: str | Path,
    *,
    text: str | None = None,
    composer: str | None = None,
    genres: Sequence[str] = (),
    moods: Sequence[str] = (),
    themes: Sequence[str] = (),
    performance_type: str | None = None,
    rights_status: str | None = None,
    min_familiarity: int | None = None,
    max_energy: int | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")
    clauses = ["1=1"]
    params: list[Any] = []
    if text:
        clauses.append("(a.title LIKE ? OR a.composer LIKE ? OR a.artist LIKE ? OR a.original_filename LIKE ?)")
        needle = f"%{text}%"
        params.extend([needle, needle, needle, needle])
    if composer:
        clauses.append("a.composer = ? COLLATE NOCASE")
        params.append(composer)
    if performance_type:
        clauses.append("a.performance_type = ?")
        params.append(performance_type)
    if rights_status:
        clauses.append("a.rights_status = ?")
        params.append(rights_status)
    if min_familiarity is not None:
        clauses.append("COALESCE(a.familiarity, 0) >= ?")
        params.append(min_familiarity)
    if max_energy is not None:
        clauses.append("COALESCE(a.energy, 3) <= ?")
        params.append(max_energy)

    for values, kind in ((genres, "genre"), (moods, "mood"), (themes, "theme")):
        for value in values:
            clauses.append(
                "EXISTS (SELECT 1 FROM asset_tags t WHERE t.asset_id=a.asset_id AND t.kind=? AND t.value=? COLLATE NOCASE)"
            )
            params.extend([kind, value])

    sql = f"""
        SELECT a.asset_id, a.title, a.composer, a.artist, a.performance_type,
               a.quality_grade, a.familiarity, a.energy, a.favorite,
               a.duration_seconds, a.rights_status, a.peak_simultaneous_notes,
               a.midi_path, a.metadata_path
        FROM assets a
        WHERE {' AND '.join(clauses)}
        ORDER BY a.favorite DESC, COALESCE(a.quality_grade, 'Z'),
                 COALESCE(a.title, a.original_filename) COLLATE NOCASE
        LIMIT ?
    """
    params.append(limit)
    with _connect(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def catalog_stats(db_path: str | Path) -> dict[str, int]:
    with _connect(db_path) as conn:
        return {
            "assets": conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0],
            "compositions": conn.execute("SELECT COUNT(*) FROM compositions").fetchone()[0],
            "genres": conn.execute("SELECT COUNT(DISTINCT value) FROM asset_tags WHERE kind='genre'").fetchone()[0],
            "moods": conn.execute("SELECT COUNT(DISTINCT value) FROM asset_tags WHERE kind='mood'").fetchone()[0],
            "themes": conn.execute("SELECT COUNT(DISTINCT value) FROM asset_tags WHERE kind='theme'").fetchone()[0],
        }


def reindex_main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild the OpenOrchestrion SQLite catalog from durable MIDI sidecars.")
    parser.add_argument("library_root", nargs="?", default="var/library")
    parser.add_argument("--db")
    parser.add_argument("--skip-invalid", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = rebuild_catalog(args.library_root, db_path=args.db, strict=not args.skip_invalid)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    else:
        print(f"rebuilt {result.db_path}: {result.indexed_assets} assets, {result.indexed_compositions} compositions")
        if result.skipped_sidecars:
            print(f"skipped {result.skipped_sidecars} invalid sidecars")


def query_main() -> None:
    parser = argparse.ArgumentParser(description="Query an OpenOrchestrion SQLite catalog.")
    parser.add_argument("db", nargs="?", default="var/library/catalog.db")
    parser.add_argument("--text")
    parser.add_argument("--composer")
    parser.add_argument("--genre", action="append", default=[])
    parser.add_argument("--mood", action="append", default=[])
    parser.add_argument("--theme", action="append", default=[])
    parser.add_argument("--performance-type")
    parser.add_argument("--rights-status")
    parser.add_argument("--min-familiarity", type=int)
    parser.add_argument("--max-energy", type=int)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--stats", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.stats:
        data: Any = catalog_stats(args.db)
    else:
        data = search_catalog(
            args.db,
            text=args.text,
            composer=args.composer,
            genres=args.genre,
            moods=args.mood,
            themes=args.theme,
            performance_type=args.performance_type,
            rights_status=args.rights_status,
            min_familiarity=args.min_familiarity,
            max_energy=args.max_energy,
            limit=args.limit,
        )
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
    elif isinstance(data, dict):
        for key, value in data.items():
            print(f"{key}: {value}")
    else:
        for row in data:
            print(f"{row['title'] or row['asset_id']} | {row['composer'] or 'Unknown'} | {row['duration_seconds']:.1f}s")


if __name__ == "__main__":
    reindex_main()
