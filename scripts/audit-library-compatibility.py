#!/usr/bin/env python3
"""Read-only, all-admitted compatibility inventory using validated source facts."""
import argparse
import json
import sqlite3
from collections import Counter
from contextlib import closing
from pathlib import Path

from openorchestrion.library.readiness import readiness, source_facts

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('catalog', type=Path)
args = parser.parse_args()
db = args.catalog.resolve()
palettes, flags, label_disagreements = Counter(), Counter(), Counter()
count = 0
with closing(sqlite3.connect(f'{db.as_uri()}?mode=ro', uri=True)) as conn:
    rows = conn.execute('SELECT asset_id,midi_path,performance_type FROM assets ORDER BY asset_id').fetchall()
for asset, path, performance_type in rows:
    facts = source_facts(db, asset, str(db.parent / path))
    preview = readiness(facts, performance_type)
    palette = preview['source_palette']['kind']
    palettes[palette] += 1
    flags.update({f['code'] for f in preview['flags']})
    if performance_type == 'MULTI_INSTRUMENT' and len(facts['parts']) == 1:
        label_disagreements[palette] += 1
    count += 1
print(json.dumps({'assets': count, 'mode': 'source without rendering overrides',
                  'source_palettes': palettes, 'flags_distinct_assets': flags,
                  'single_channel_multi_instrument_labels': label_disagreements,
                  'mutations': 0}, indent=2, sort_keys=True))
