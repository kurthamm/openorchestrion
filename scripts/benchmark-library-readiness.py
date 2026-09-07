import argparse
import json
import sqlite3
import time
from pathlib import Path
from openorchestrion.library.browse import browse, browse_facets
from openorchestrion.playback import (
    PlaybackEngine,
    MidiOutputRouter,
    VirtualMidiOutput,
    SystemClock,
)
from openorchestrion.playback.timeline import MidiTimeline

parser = argparse.ArgumentParser(
    description="Measure library query and virtual preparation costs without playing hardware."
)
parser.add_argument("catalog", type=Path)
parser.add_argument("output", type=Path)
parser.add_argument("--library-root", type=Path)
args = parser.parse_args()
db = args.catalog.resolve()
with sqlite3.connect(db) as conn:
    rows = conn.execute(
        "SELECT asset_id,midi_path,note_count FROM assets ORDER BY note_count,asset_id"
    ).fetchall()


def measure(fn, n=5):
    result = []
    for _ in range(n):
        start = time.perf_counter()
        fn()
        result.append(round((time.perf_counter() - start) * 1000, 3))
    return result


clock = SystemClock()
engine = PlaybackEngine(
    router=MidiOutputRouter([VirtualMidiOutput("Benchmark only", clock)]), history=None, clock=clock
)
result = {
    "kind": "virtual preparation, no hardware sends",
    "facets_ms": measure(lambda: browse_facets(db)),
    "search_ms": measure(lambda: browse(db, text="bach")),
    "assets": [],
}
for index in [len(rows) // 2, len(rows) * 9 // 10, len(rows) * 99 // 100]:
    asset, path, notes = rows[index]
    path = (args.library_root or db.parent) / path

    def cold():
        timeline = MidiTimeline.from_file(path)
        engine._build_dispatches(timeline, None)

    def warm():
        timeline = (
            engine._load_source(path)
            if hasattr(engine, "_load_source")
            else MidiTimeline.from_file(path)
        )
        engine._build_dispatches(timeline, None)

    cold_times = measure(cold, 3)
    warm()
    warm_times = measure(warm, 3)
    result["assets"].append(
        {
            "asset_id": asset,
            "notes": notes,
            "cold_prepare_ms": cold_times,
            "repeat_prepare_ms": warm_times,
        }
    )
print(json.dumps(result, indent=2))
args.output.write_text(json.dumps(result, indent=2) + "\n")
