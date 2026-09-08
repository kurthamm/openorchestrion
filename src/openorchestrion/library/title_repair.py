"""Plan, apply or reverse a metadata-only identity repair with conflict checks."""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from contextlib import closing

from .acquisition_publish import snapshot_lock, _write
from .catalog import rebuild_catalog
from .metadata import read_metadata, update_metadata, normalize_metadata
from .title_identity import source_identity, decode_label


def proposal(document: dict) -> dict:
    before = document['descriptive_metadata']
    after = deepcopy(before)
    if before.get('source_title'):
        return after  # Already reviewed; never overwrite a later human correction.
    provenance = document.get('provenance') or {}
    title = before.get('title')
    if not title:
        return after
    if provenance.get('source_label') == 'BitMidi':
        attribution = provenance.get('attribution', '')
        match = re.fullmatch(r"BitMidi upload '(.*)' \(original sequencer unknown\)", attribution)
        raw = match[1] if match else title
        # Only normalize legacy uploader-derived titles. Other curated edits are
        # left alone, even if they happen to contain punctuation.
        legacy = re.sub(r'\.midi?$', '', raw, flags=re.I).replace('_', ' ').strip()
        legacy = re.sub(r'\s*\(\d+\)$', '', legacy)
        split = re.match(r'^(.{2,60}?)\s+-\s+(.+)$', legacy)
        prefix, old_title = split.groups() if split else ('', legacy)
        if title != old_title:
            return after
        identity = source_identity(raw, source='BitMidi')
        after.update(identity)
        for field in ('artist', 'composer'):
            if prefix and before.get(field) == prefix:
                after.pop(field, None)
                after['source_context'] = decode_label(prefix)
                after['metadata_note'] = (
                    identity.get('metadata_note', '') +
                    ' Upload prefix retained as source context; it does not establish a creator credit.'
                ).strip()
    else:
        for field in ('title', 'composition_title', 'composer', 'artist'):
            if before.get(field):
                after[field] = decode_label(before[field])
        if after != before:
            after['source_title'] = title
    return normalize_metadata(after)


def make_plan(root: Path, *, overrides: list[dict] = ()) -> dict:
    root = root.resolve()
    decisions = {r['asset_id']: r for r in overrides}
    with closing(sqlite3.connect(root / 'catalog.db')) as conn:
        ids = [r[0] for r in conn.execute('SELECT asset_id FROM assets ORDER BY asset_id')]
    entries = []
    for asset_id in ids:
        path = root / 'assets' / (asset_id.split(':')[-1] + '.json')
        document = json.loads(path.read_bytes())
        before = document['descriptive_metadata']
        after = proposal(document)
        if asset_id in decisions:
            import mido
            decision = decisions[asset_id]
            if before.get('title') != decision['original_title']:
                raise ValueError(f'Override title changed: {asset_id}')
            midi = path.with_suffix('.mid')
            if hashlib.sha256(midi.read_bytes()).hexdigest() != asset_id.split(':')[-1]:
                raise ValueError(f'MIDI digest mismatch: {asset_id}')
            texts = [str(getattr(m, 'text', getattr(m, 'name', ''))).strip()
                     for track in mido.MidiFile(midi).tracks for m in track
                     if m.type in ('track_name', 'text', 'copyright')]
            if not all(any(e in text for text in texts) for e in decision['required_text']):
                raise ValueError(f'Embedded evidence mismatch: {asset_id}')
            after.update(decision['changes'])
            after['title_status'] = 'embedded_metadata'
            after['metadata_note'] = decision['basis']
            after = normalize_metadata(after)
        if after != before:
            record = read_metadata(root, asset_id)
            entries.append({'asset_id': asset_id, 'before': before, 'after': after,
                            'before_revision': record.revision})
    return {'version': 1, 'root': str(root), 'inventory': ids, 'entries': entries}


def execute_plan(root: Path, plan: dict, *, rollback: bool = False) -> dict:
    """Resumable writes; unrelated changes cause a refusal, never an overwrite.

    The saved plan is the durable before/after journal. If interrupted, rerun the
    same plan. Reindexing is atomic and always runs, including after a resumed run.
    """
    root = root.resolve()
    if plan.get('version') != 1 or plan['root'] != str(root):
        raise ValueError('Plan does not describe this library')
    source, target = ('after', 'before') if rollback else ('before', 'after')
    with snapshot_lock(root):
        with closing(sqlite3.connect(root / 'catalog.db')) as conn:
            current_ids = [r[0] for r in conn.execute('SELECT asset_id FROM assets ORDER BY asset_id')]
        if current_ids != plan['inventory']:
            raise ValueError('Library inventory changed since the plan; create a fresh plan')
        records = {}
        for entry in plan['entries']:
            record = read_metadata(root, entry['asset_id'])
            if record.descriptive_metadata not in (entry[source], entry[target]):
                raise ValueError(f"Metadata changed since the plan: {entry['asset_id']}")
            if not rollback and record.descriptive_metadata == entry['before'] and record.revision != entry['before_revision']:
                raise ValueError(f"Sidecar changed since the plan: {entry['asset_id']}")
            records[entry['asset_id']] = record
        changed = 0
        for entry in plan['entries']:
            record = records[entry['asset_id']]
            if record.descriptive_metadata != entry[target]:
                update_metadata(root, entry['asset_id'], entry[target],
                                remove=set(record.descriptive_metadata) - set(entry[target]),
                                expected_revision=record.revision)
                changed += 1
        result = rebuild_catalog(root)
        with closing(sqlite3.connect(root / 'catalog.db')) as conn:
            ids = [r[0] for r in conn.execute('SELECT asset_id FROM assets ORDER BY asset_id')]
        if ids != plan['inventory']:
            raise ValueError('Library inventory changed; inspect the retained plan')
        return {'changed': changed, 'indexed': result.indexed_assets, 'rollback': rollback}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library-root', required=True, type=Path)
    parser.add_argument('--plan', required=True, type=Path)
    parser.add_argument('--overrides', type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--apply', action='store_true')
    modes.add_argument('--rollback', action='store_true')
    args = parser.parse_args()
    if args.apply or args.rollback:
        print(json.dumps(execute_plan(args.library_root, json.loads(args.plan.read_bytes()), rollback=args.rollback)))
    else:
        if args.plan.exists():
            parser.error('Refusing to overwrite an existing rollback plan')
        overrides = json.loads(args.overrides.read_bytes()) if args.overrides else []
        with snapshot_lock(args.library_root):
            plan = make_plan(args.library_root, overrides=overrides)
            _write(args.plan, (json.dumps(plan, indent=2) + '\n').encode())
        print(json.dumps({'planned': len(plan['entries']), 'inventory': len(plan['inventory'])}))


if __name__ == '__main__':
    main()
