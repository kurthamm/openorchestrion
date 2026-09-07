#!/usr/bin/env python3
"""Deterministic, source-stratified raw MIDI inventory; no quality score or writes."""
import argparse
import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from contextlib import closing
from pathlib import Path

from openorchestrion.library.midi_scan import read_events

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('catalog', type=Path)
parser.add_argument('--per-source', type=int, default=24)
args = parser.parse_args()
db = args.catalog.resolve()
with closing(sqlite3.connect(f'{db.as_uri()}?mode=ro', uri=True)) as conn:
    conn.row_factory = sqlite3.Row
    rows = [dict(row) for row in conn.execute(
        'SELECT asset_id,title,source_label,source_reference,midi_path FROM assets ORDER BY asset_id')]
sources = defaultdict(list)
for row in rows:
    sources[row['source_label']].append(row)
selected = {}
for group in sources.values():
    ranked = sorted(group, key=lambda r: hashlib.sha256(('content-research-v1:'+r['asset_id']).encode()).hexdigest())
    for row in ranked[:args.per_source]:
        selected[row['asset_id']] = (row, 'source_stratified')
targets = ['0006b7e40086c796bb177d89038118cb896bdbd1b3ef7c7cb32de04fc6ef84f5',
           '037b5447d3be6b8b9e83de090c5eb2aac38705fec8d6c51eafcdb55fd742fd54',
           '2f6b9ef0ed6510ca44e09faa7338b1f86af02c5eb3e32b5e6cd5b81685db6e88']
for row in rows:
    if row['asset_id'].removeprefix('sha256:') in targets:
        selected.setdefault(row['asset_id'], (row, 'targeted_example'))
result = []
summary = defaultdict(Counter)
for row, selection in selected.values():
    raw = (db.parent / row['midi_path']).read_bytes()
    assert 'sha256:' + hashlib.sha256(raw).hexdigest() == row['asset_id']
    kind, division, events = read_events(raw)
    meta, messages, velocities = Counter(), Counter(), Counter()
    controllers, programs = defaultdict(set), defaultdict(set)
    tempo_values, channels = set(), set()
    for tick, track, sequence, status, data in events:
        if status == 255:
            meta[f'0x{data[0]:02x}'] += 1
            if data[0] == 81:
                tempo_values.add(int.from_bytes(data[1:], 'big'))
        elif status == 240:
            messages['sysex'] += 1
        else:
            op, channel = status >> 4, status & 15
            messages[f'0x{op:x}'] += 1
            if op == 9 and data[1]:
                velocities[data[1]] += 1
                channels.add(channel + 1)
            elif op == 11:
                controllers[(channel + 1, data[0])].add(data[1])
            elif op == 12:
                programs[channel + 1].add(data[0] + 1)
    record = {key: value for key, value in row.items() if key != 'midi_path'}
    record.update(selection=selection, format=kind, ticks_per_beat=division,
                  sounding_channels=sorted(channels), notes=sum(velocities.values()),
                  unique_velocities=len(velocities), modal_velocity_fraction=round(max(velocities.values(), default=0)/max(1,sum(velocities.values())),4),
                  meta_event_counts=meta, message_counts=messages,
                  tempo_values=len(tempo_values), programs={str(k):sorted(v) for k,v in programs.items()},
                  controllers=[{'channel':ch,'cc':cc,'distinct_values':len(values),'min':min(values),'max':max(values)} for (ch,cc),values in sorted(controllers.items())])
    result.append(record)
    if selection == 'source_stratified':
        c = summary[row['source_label']]
        c['sampled'] += 1
        for label, present in {
            'multiple_velocities':len(velocities)>1, 'tempo_events':bool(tempo_values),
            'multiple_tempo_values':len(tempo_values)>1, 'program_changes':bool(programs),
            'sysex':bool(messages['sysex']), 'lyrics':bool(meta['0x05']),
            'track_names':bool(meta['0x03']), 'copyright':bool(meta['0x02']),
            'sustain_cc64':any(cc == 64 for ch,cc in controllers),
            'sostenuto_cc66':any(cc == 66 for ch,cc in controllers),
            'soft_cc67':any(cc == 67 for ch,cc in controllers),
            'expression_cc11':any(cc == 11 for ch,cc in controllers),
            'pitch_bend':bool(messages['0xe']),
        }.items():
            c[label] += int(present)
print(json.dumps({'selection':'SHA256(content-research-v1:asset_id), first N per source; targeted examples separate',
                  'per_source':args.per_source,'files':len(result),'source_sample_summary':summary,
                  'records':result,'mutations':0},indent=2,sort_keys=True))
