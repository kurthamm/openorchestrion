import argparse
import json
import sqlite3
import collections
import datetime
from pathlib import Path
from openorchestrion.library.readiness import readiness, VERSION

parser = argparse.ArgumentParser(
    description="Compare a rebuilt playback facts index with its admitted catalog."
)
parser.add_argument("catalog", type=Path)
parser.add_argument("output", type=Path)
args = parser.parse_args()
db = args.catalog.resolve()
root = db.parent
with sqlite3.connect(f"{db.as_uri()}?mode=ro", uri=True) as catalog:
    rows = catalog.execute(
        "SELECT asset_id,performance_type,note_count,peak_simultaneous_notes,duration_seconds FROM assets"
    ).fetchall()
with sqlite3.connect(f"file:{root}/playback-facts.sqlite3?mode=ro", uri=True) as cache:
    facts = {
        r[0]: json.loads(r[1])
        for r in cache.execute("SELECT asset_id,facts FROM facts WHERE version=?", (VERSION,))
    }
counts = collections.Counter()
mismatch = []
examples = {}
for asset, arrangement, notes, peak, duration in rows:
    if asset not in facts:
        continue
    f = facts[asset]
    r = readiness(f, arrangement)
    counts["parts"] += len(f["parts"])
    for flag in r["flags"]:
        counts[flag["code"]] += 1
        examples.setdefault(flag["code"], asset)
    if (
        sum(p["note_count"] for p in f["parts"]) != notes
        or f["peak_notes"] != peak
        or abs(f["duration_seconds"] - duration) > 1e-5
    ):
        mismatch.append(
            {
                "asset_id": asset,
                "catalog_notes": notes,
                "facts_notes": sum(p["note_count"] for p in f["parts"]),
                "catalog_peak": peak,
                "facts_peak": f["peak_notes"],
                "catalog_duration": duration,
                "facts_duration": f["duration_seconds"],
            }
        )
result = {
    "at": datetime.datetime.now(datetime.UTC).isoformat(),
    "version": VERSION,
    "admitted": len(rows),
    "indexed": len(set(r[0] for r in rows) & set(facts)),
    "missing": len(set(r[0] for r in rows) - set(facts)),
    "source_counts": counts,
    "examples": examples,
    "catalog_mismatches": mismatch,
}
args.output.write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps({**result, "catalog_mismatches": len(mismatch)}, indent=2))

if result["missing"] or mismatch:
    raise SystemExit(1)
