"""Autonomous incremental discovery, qualification and additive publication."""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
from urllib.error import HTTPError
import zipfile

from .acquisition_sources import SOURCES, Client, api_page, page_links
from .acquisition_publish import publish, _write, snapshot_lock
from .quality import VERSION


def connect(root):
    conn = sqlite3.connect(root / "acquisition.sqlite3", timeout=20)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS decisions(asset_id TEXT PRIMARY KEY, record TEXT);
        CREATE TABLE IF NOT EXISTS known(asset_id TEXT PRIMARY KEY, fingerprint TEXT, reference TEXT, verdict TEXT);
        CREATE INDEX IF NOT EXISTS known_fingerprint ON known(fingerprint);
        CREATE TABLE IF NOT EXISTS sources(source TEXT PRIMARY KEY, cursor TEXT DEFAULT '', report TEXT DEFAULT '{}', retry_at REAL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS frontier(source TEXT, url TEXT, payload TEXT, due REAL DEFAULT 0, attempts INTEGER DEFAULT 0, PRIMARY KEY(source,url));
        CREATE TABLE IF NOT EXISTS runs(started REAL PRIMARY KEY, report TEXT);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
    """)
    return conn


def inventory(root):
    return {"sha256:" + p.stem for p in root.glob("assets/*.json")} | {
        "sha256:" + p.stem for p in root.glob("archive/*/assets/*.json")
    }


def initialize_empty(root: Path):
    """Create a fresh quality-gated library without deployment-private evidence.

    Existing collections must be assessed and seeded; this command cannot clear
    admission, discarded identities, or a partially imported collection.
    """
    from .acquisition_publish import publication_lock
    from .catalog import rebuild_catalog

    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    with snapshot_lock(root), publication_lock(root):
        if any(p.is_file() for directory in (root / "assets", root / "archive")
               for p in directory.rglob("*")):
            raise ValueError("--init-empty refuses an existing collection; assess and seed it")
        manifest_path = root / "listening-admission.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_bytes())
            if manifest.get("policy_version") != VERSION or manifest.get("asset_ids") != []:
                raise ValueError("--init-empty cannot replace an existing admission policy")
        (root / "assets").mkdir(exist_ok=True)
        with closing(sqlite3.connect(root / "quality.sqlite3")) as conn, conn:
            conn.execute("CREATE TABLE IF NOT EXISTS quality(asset_id TEXT PRIMARY KEY, record TEXT)")
        with closing(connect(root)) as conn, conn:
            conn.execute("INSERT OR IGNORE INTO settings VALUES (?,?)", ("bootstrap", "empty-v2"))
        if not manifest_path.exists():
            _write(manifest_path, json.dumps({"policy_version": VERSION, "asset_ids": [],
                                            "origin": "empty-library"}).encode())
        rebuild_catalog(root)
    return {"initialized": True, "library_root": str(root), "policy_version": VERSION}


def seed(root, archive, expected_sha):
    """Bootstrap all previous decisions; existing rejections must not be reacquired."""
    with zipfile.ZipFile(archive) as z:
        raw = z.read("quality-facts.jsonl")
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise ValueError("bootstrap facts checksum mismatch")
    records = [json.loads(line) for line in raw.splitlines()]
    if {r["asset_id"] for r in records} != inventory(root):
        raise ValueError("bootstrap facts do not cover the exact original inventory")
    with closing(connect(root)) as conn, conn:
        conn.executemany(
            "INSERT OR IGNORE INTO known VALUES (?,?,?,?)",
            [
                (
                    r["asset_id"],
                    r.get("facts", {}).get("fingerprint"),
                    r.get("provenance", {}).get("source_reference"),
                    "baseline",
                )
                for r in records
            ],
        )
        conn.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", ("seed_sha256", expected_sha))
    return len(records)


def enqueue(conn, source, items):
    available = max(
        0,
        100000
        - conn.execute("SELECT count(*) FROM frontier WHERE source=?", (source.key,)).fetchone()[0],
    )
    items = items[:available]
    if source.key == "bitmidi":
        items = [
            i
            for i in items
            if not conn.execute(
                "SELECT 1 FROM known WHERE reference=?", (i["reference"],)
            ).fetchone()
        ]
    conn.executemany(
        "INSERT OR IGNORE INTO frontier(source,url,payload) VALUES (?,?,?)",
        [(source.key, i["url"], json.dumps(i)) for i in items],
    )
    conn.commit()


def known_record(conn, record):
    conn.execute(
        "INSERT OR REPLACE INTO decisions VALUES (?,?)", (record["asset_id"], json.dumps(record))
    )
    conn.execute(
        "INSERT OR REPLACE INTO known VALUES (?,?,?,?)",
        (
            record["asset_id"],
            record.get("facts", {}).get("fingerprint"),
            record.get("provenance", {}).get("source_reference"),
            record["status"],
        ),
    )
    conn.commit()


def evaluate(root, state, conn, source, item, client):
    reference = item["reference"]
    if (
        source.key == "bitmidi"
        and conn.execute("SELECT 1 FROM known WHERE reference=?", (reference,)).fetchone()
    ):
        return "known_source"
    if shutil.disk_usage(state).free < 512 * 1024 * 1024:
        raise RuntimeError("less than 512 MiB free; acquisition deferred")
    raw = client.get(item["url"], limit=2 * 1024 * 1024)
    digest = hashlib.sha256(raw).hexdigest()
    asset = "sha256:" + digest
    if conn.execute("SELECT 1 FROM known WHERE asset_id=?", (asset,)).fetchone():
        return "duplicate_bytes"
    directory = state / "staging" / digest
    directory.mkdir(parents=True, exist_ok=True)
    _write(directory / "download.mid", raw)
    candidate = dict(
        item,
        label=source.label,
        genre=source.genre,
        license=source.license,
        license_url=source.license_url,
    )
    if source.key == "classical-archives":
        candidate["attribution"] = (
            "Sequence Â© Pierre R. Schwob â€” by permission. Original from Classical Archives."
        )
    _write(directory / "candidate.json", json.dumps(candidate).encode())
    try:
        subprocess.run(
            [sys.executable, "-m", "openorchestrion.library.acquisition_worker", str(directory)],
            check=True,
            timeout=60,
            capture_output=True,
        )
        record = json.loads((directory / "result.json").read_bytes())
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        detail = (getattr(exc, "stderr", b"") or b"").decode("utf-8", "replace")[-500:]
        raise RuntimeError(
            "assessment worker failed; candidate retained for retry: " + detail
        ) from exc
    record["download_url"] = item["url"]
    if record["status"] == "qualified":
        duplicate = conn.execute(
            "SELECT asset_id FROM known WHERE fingerprint=? LIMIT 1",
            (record["facts"]["fingerprint"],),
        ).fetchone()
        if duplicate:
            record.update(
                status="excluded",
                reasons=["duplicate_timed_playback"],
                retained_asset_id=duplicate[0],
            )
    if record["status"] == "qualified":
        journal = state / "publications" / (digest + ".json")
        journal.parent.mkdir(exist_ok=True)
        publish(root, journal, record)
        verdict = "admitted"
    else:
        verdict = (
            "duplicate_playback"
            if "duplicate_timed_playback" in record["reasons"]
            else "not_qualified"
        )
    # Persist measured reasons and provenance, even for rejected downloads.
    decisions = state / "decisions"
    decisions.mkdir(exist_ok=True)
    _write(decisions / (digest + ".json"), json.dumps(record).encode())
    known_record(conn, record)
    shutil.rmtree(directory)  # Only this hash-named, privately owned staging directory.
    return verdict


def run_source(root, state, conn, source, limit, page_limit):
    counts = Counter()
    report = {
        "source": source.label,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "counts": counts,
    }
    if source.disabled:
        return report | {"status": "disabled", "reason": source.disabled}
    conn.execute("INSERT OR IGNORE INTO sources(source) VALUES (?)", (source.key,))
    row = conn.execute(
        "SELECT cursor,retry_at FROM sources WHERE source=?", (source.key,)
    ).fetchone()
    if row[1] > time.time():
        return report | {"status": "backoff", "retry_at": row[1]}
    client = Client(source)
    enqueue(
        conn,
        source,
        [{"url": s, "kind": "page", "title": source.label, "reference": s} for s in source.seeds],
    )
    pages, processed = 0, 0
    try:
        # Metadata-only index pages advance persistently; candidates remain queued
        # when a night's download budget ends, so nothing is lost at page boundaries.
        if source.key in ("bitmidi", "commons"):
            ready = conn.execute(
                "SELECT count(*) FROM frontier WHERE source=? AND due<=?", (source.key, time.time())
            ).fetchone()[0]
            while ready < limit and pages < page_limit:
                items, cursor, reference = api_page(source, client, row[0])
                enqueue(conn, source, items)
                conn.execute("UPDATE sources SET cursor=? WHERE source=?", (cursor, source.key))
                conn.commit()
                counts["index_pages"] += 1
                pages += 1
                row = (cursor, 0)
                ready = conn.execute(
                    "SELECT count(*) FROM frontier WHERE source=? AND due<=?",
                    (source.key, time.time()),
                ).fetchone()[0]
                if cursor in ("", "0"):
                    break
        while processed < limit:
            row = conn.execute(
                "SELECT url,payload,attempts FROM frontier WHERE source=? AND due<=? AND (json_extract(payload,'$.kind')='midi' OR ?) ORDER BY CASE json_extract(payload,'$.kind') WHEN 'midi' THEN 0 ELSE 1 END,due,rowid LIMIT 1",
                (source.key, time.time(), pages < page_limit),
            ).fetchone()
            if row is None:
                break
            url, payload, attempts = row
            item = json.loads(payload)
            try:
                if item["kind"] == "page":
                    raw = client.get(url)
                    items = page_links(source, url, raw)
                    if (
                        source.key == "smd"
                        and url in source.seeds
                        and b"Version 2" in raw
                        and b"Disklavier" in raw
                        and b"control messages" in raw
                    ):
                        for linked in items:
                            if linked["kind"] == "midi":
                                linked["publisher_capture"] = {
                                    "completeness": "complete",
                                    "performance_capture": True,
                                    "arrangement": "solo_piano",
                                    "source": url,
                                    "basis": "Exact MIDI link from the publisher SMD version 2 piano-performance table, retaining documented pedal controls",
                                    "metadata_sha256": hashlib.sha256(raw).hexdigest(),
                                    "download_url": linked["url"],
                                }
                    enqueue(conn, source, items)
                    pages += 1
                    counts["listing_pages"] += 1
                    due = time.time() + 7 * 86400
                else:
                    verdict = evaluate(root, state, conn, source, item, client)
                    counts[verdict] += 1
                    processed += 1
                    due = time.time() + 30 * 86400
                conn.execute(
                    "UPDATE frontier SET due=?,attempts=0 WHERE source=? AND url=?",
                    (due, source.key, url),
                )
                conn.commit()
            except (HTTPError, OSError, ValueError, RuntimeError) as exc:
                delay = min(7 * 86400, 3600 * 2 ** min(attempts, 7))
                if isinstance(exc, HTTPError):
                    from email.utils import parsedate_to_datetime

                    retry = exc.headers.get("Retry-After", "")
                    try:
                        delay = max(
                            delay,
                            float(retry)
                            if retry.isdigit()
                            else parsedate_to_datetime(retry).timestamp() - time.time(),
                        )
                    except (ValueError, TypeError):
                        pass
                conn.execute(
                    "UPDATE frontier SET due=?,attempts=attempts+1 WHERE source=? AND url=?",
                    (time.time() + delay, source.key, url),
                )
                conn.commit()
                raise RuntimeError(f"{url}: {type(exc).__name__}: {exc}") from exc
        report["status"] = "ok"
    except (HTTPError, OSError, ValueError, RuntimeError) as exc:
        report.update(status="error", error=str(exc)[:1000])
        conn.execute(
            "UPDATE sources SET retry_at=? WHERE source=?", (time.time() + 86400, source.key)
        )
        conn.commit()
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    return report


def run(root, state, *, limit=20, page_limit=8, only=None):
    import fcntl

    state.mkdir(parents=True, exist_ok=True)
    with (
        snapshot_lock(root),
        (state / "worker.lock").open("w") as lock,
        closing(connect(root)) as conn,
    ):
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        manifest = json.loads((root / "listening-admission.json").read_bytes())
        if manifest.get("policy_version") != VERSION:
            raise ValueError("acquisition requires the v2 admission policy")
        for journal in sorted((state / "publications").glob("*.json")):
            record = json.loads(journal.read_bytes())
            if not record.get("published"):
                record = publish(root, journal)
            if not conn.execute(
                "SELECT 1 FROM known WHERE asset_id=?", (record["asset_id"],)
            ).fetchone():
                known_record(conn, record)
            # Reconcile a catalog rebuilt concurrently after an earlier publication.
            with closing(sqlite3.connect(root / "catalog.db")) as catalog:
                indexed = catalog.execute(
                    "SELECT 1 FROM assets WHERE asset_id=?", (record["asset_id"],)
                ).fetchone()
            if not indexed and record["asset_id"] in manifest["asset_ids"]:
                from .catalog import reindex_asset

                reindex_asset(root / "catalog.db", root, record["asset_id"])
        pending = {
            Path(json.loads(j.read_bytes())["stage"]).parents[2]
            for j in (state / "publications").glob("*.json")
            if not json.loads(j.read_bytes()).get("published")
        }
        for directory in (state / "staging").glob("*"):
            if (
                directory.is_dir()
                and directory not in pending
                and time.time() - directory.stat().st_mtime > 7 * 86400
            ):
                shutil.rmtree(directory)
        missing = inventory(root) - {r[0] for r in conn.execute("SELECT asset_id FROM known")}
        if missing:
            raise ValueError(
                f"{len(missing)} existing originals lack duplicate-history coverage; seed before scanning"
            )
        started = time.time()
        progress = {"status": "running", "started_at": started, "sources": []}
        save_status(conn, progress)
        reports = []
        for source in SOURCES:
            if only and source.key not in only:
                continue
            report = run_source(root, state, conn, source, limit, page_limit)
            reports.append(report)
            conn.execute(
                "INSERT INTO sources(source,report) VALUES (?,?) ON CONFLICT(source) DO UPDATE SET report=excluded.report",
                (source.key, json.dumps(report)),
            )
            conn.commit()
            save_status(conn, progress | {"sources": reports})
            print(json.dumps(report), flush=True)
        total = Counter()
        for r in reports:
            total.update(r["counts"])
        report = {
            "status": "degraded" if any(r["status"] == "error" for r in reports) else "ok",
            "started_at": started,
            "finished_at": time.time(),
            "counts": total,
            "sources": reports,
            "policy_version": VERSION,
        }
        conn.execute("INSERT INTO runs VALUES (?,?)", (started, json.dumps(report)))
        conn.commit()
        save_status(conn, report)
        _write(state / "status.json", json.dumps(report).encode())
        return report


def save_status(conn, report):
    conn.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", ("status", json.dumps(report)))
    conn.commit()


def status(root):
    path = root / "acquisition.sqlite3"
    if not path.exists():
        return {"status": "not_configured", "sources": []}
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=2)) as conn:
        row = conn.execute("SELECT value FROM settings WHERE key='status'").fetchone()
    report = json.loads(row[0]) if row else {"status": "not_run", "sources": []}
    if report["status"] == "running" and time.time() - report["started_at"] > 45 * 60:
        report = report | {
            "status": "interrupted",
            "error": "The last acquisition run did not finish within its service time budget.",
        }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--library-root", type=Path, default=Path("/var/lib/openorchestrion/library")
    )
    parser.add_argument(
        "--state-root", type=Path, default=Path("/var/lib/openorchestrion/acquisition")
    )
    parser.add_argument(
        "--limit", type=int, default=20, help="Maximum MIDI candidates per source per run"
    )
    parser.add_argument("--page-limit", type=int, default=8)
    parser.add_argument("--source", action="append", choices=[s.key for s in SOURCES])
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--init-empty", action="store_true", help="Initialize a new empty quality-gated library")
    modes.add_argument("--seed-zip", type=Path)
    parser.add_argument("--facts-sha256")
    modes.add_argument("--status", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.limit <= 200 or not 1 <= args.page_limit <= 40:
        parser.error("invalid work budget")
    if args.init_empty:
        try:
            print(json.dumps(initialize_empty(args.library_root), indent=2))
        except (OSError, ValueError, RuntimeError) as exc:
            parser.exit(2, f"error: {exc}\n")
    elif args.seed_zip:
        print(json.dumps({"seeded": seed(args.library_root, args.seed_zip, args.facts_sha256)}))
    elif args.status:
        print(json.dumps(status(args.library_root.resolve()), indent=2))
    else:
        try:
            report = run(
                args.library_root.resolve(),
                args.state_root.resolve(),
                limit=args.limit,
                page_limit=args.page_limit,
                only=args.source,
            )
        except Exception as exc:
            with closing(connect(args.library_root)) as conn:
                save_status(
                    conn,
                    {
                        "status": "failed",
                        "error": str(exc)[:1000],
                        "finished_at": time.time(),
                        "sources": [],
                    },
                )
            raise
        print(json.dumps(report, indent=2))
        enabled = [s for s in report["sources"] if s["status"] != "disabled"]
        if enabled and all(s["status"] in ("error", "backoff") for s in enabled):
            raise SystemExit(1)


if __name__ == "__main__":
    main()
