from __future__ import annotations

import hashlib
import io
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient
from mido import Message as M, MetaMessage as Meta, MidiFile, MidiTrack
from mido.midifiles.meta import UnknownMetaMessage

from openorchestrion.api.settings import Settings
from openorchestrion.app import create_app
from openorchestrion.library.browse import browse_facets
from openorchestrion.library.catalog import rebuild_catalog
from openorchestrion.library.importer import import_paths
from openorchestrion.library.readiness import VERSION, _signature, analyze_parts, readiness, source_facts
from openorchestrion.midi.analyzer import analyze_midifile, analyze_midi
from openorchestrion.playback import ManualClock, MidiOutputRouter, PlaybackEngine, VirtualMidiOutput
from openorchestrion.playback.rendering import RenderingPolicy, render_timeline
from openorchestrion.playback.timeline import MidiTimeline


def raw_midi(*tracks):
    midi = MidiFile(type=1)
    midi.tracks = [MidiTrack(t) for t in tracks]
    out = io.BytesIO()
    midi.save(file=out)
    return out.getvalue()


def test_shared_channel_state_and_bank_latching():
    raw = raw_midi([
        M('control_change', control=0, value=7, time=10),
        M('program_change', program=40, time=10),
    ], [Meta('track_name', name='Real part'),
        M('note_on', note=60, velocity=80),
        M('note_off', note=60, time=5),
        M('note_on', note=62, velocity=70, time=10),
        M('note_off', note=62, time=1),
        M('note_on', note=64, velocity=90, time=10)])
    facts = analyze_parts(raw)
    part = facts['parts'][0]
    assert part['tracks'] == [{'index': 1, 'name': 'Real part'}]
    assert [(s['program'], s['bank_msb'], s['implicit'], s['note_count']) for s in part['sounds']] == [(1, 0, True, 2), (41, 7, False, 1)]
    assert 'unverified_sound_mapping' in [f['code'] for f in readiness(facts, None)['flags']]
    assert 'sparse_arrangement' in [f['code'] for f in readiness(facts, 'MULTI_INSTRUMENT')['flags']]


def test_unknown_meta_retains_elapsed_time_in_analysis_and_playback(tmp_path):
    raw = raw_midi([M('note_on', note=60),
                    UnknownMetaMessage(0x53, data=(1, 2, 3), time=480),
                    M('note_off', note=60, time=480)])
    path = tmp_path / 'unknown-meta.mid'
    path.write_bytes(raw)
    assert analyze_parts(raw)['duration_seconds'] == 1.0
    assert analyze_midi(path).duration_seconds == 1.0
    timeline = MidiTimeline.from_file(path)
    assert timeline.duration_seconds == 1.0
    assert timeline.events[-1].at_seconds == 1.0


def test_sustain_retrigger_and_piano_only_do_not_inflate_or_include_drums():
    raw = raw_midi([
        M('control_change', control=64, value=127),
        M('note_on', note=60), M('note_off', note=60),
        M('note_on', note=60), M('note_off', note=60),
        M('note_on', note=64), M('note_on', channel=9, note=36),
        M('control_change', control=123, value=0),
        M('control_change', control=64, value=0),
    ])
    facts = analyze_parts(raw)
    assert facts['peak_notes'] == 3
    assert facts['melodic_peak_notes'] == 2
    assert facts['parts'][0]['sustain']
    assert facts['parts'][1]['sounds'][0]['name'] == 'Standard drum kit'
    preview = readiness(facts, 'solo', RenderingPolicy.from_values(mode='PIANO_ONLY', piano_program=2))
    assert preview['peak_notes'] == 2
    assert len(preview['parts']) == 1
    assert preview['parts'][0]['sounds'][0]['program'] == 3
    assert facts['parts'][0]['sounds'][0]['program'] == 1  # no source mutation
    assert 'sparse_arrangement' not in [f['code'] for f in preview['flags']]


def test_no_notes_and_reference_capacity_are_honest():
    empty = readiness(analyze_parts(raw_midi([M('program_change', program=4)])), None)
    assert empty['status'] == 'caution'
    assert not empty['parts']
    dense = readiness(analyze_parts(raw_midi([M('note_on', note=n) for n in range(49)])), None)
    assert 'wk220_over_48' in [f['code'] for f in dense['flags']]
    assert 'not a listening-quality rating' in dense['limitation']


def test_source_cache_rejects_changed_content(tmp_path):
    path = tmp_path / 'song.mid'
    raw = raw_midi([M('note_on', note=60), M('note_off', note=60, time=480)])
    path.write_bytes(raw)
    asset = 'sha256:' + hashlib.sha256(raw).hexdigest()
    db = tmp_path / 'catalog.db'
    facts = source_facts(db, asset, str(path))
    with sqlite3.connect(tmp_path / 'playback-facts.sqlite3') as conn:
        conn.execute('CREATE TABLE facts(asset_id TEXT,version INTEGER,signature TEXT,facts TEXT)')
        conn.execute('INSERT INTO facts VALUES(?,?,?,?)', (asset, VERSION, _signature(path), json.dumps(facts)))
    assert source_facts(db, asset, str(path)) == facts
    path.write_bytes(raw_midi([M('note_on', note=61)]))
    with pytest.raises(ValueError, match='no longer matches'):
        source_facts(db, asset, str(path))


def library(tmp_path):
    source = tmp_path / 'song.mid'
    source.write_bytes(raw_midi([M('program_change', program=40), M('note_on', note=60), M('note_off', note=60, time=480)]))
    root = tmp_path / 'library'
    assert not import_paths([source], root).failed
    rebuild_catalog(root)
    asset = 'sha256:' + hashlib.sha256(source.read_bytes()).hexdigest()
    return root, asset


def test_preview_matches_queue_policy_without_mutating_transport(tmp_path):
    root, asset = library(tmp_path)
    with TestClient(create_app(settings=Settings(library_root=root, catalog_db=root / 'catalog.db', history_db=root / 'history.db', virtual_midi=True))) as client:
        before = client.get('/api/queue').json()
        policy = {'mode': 'PIANO_ONLY', 'piano_program': 2}
        response = client.post(f'/api/library/assets/{asset}/performance/preview', json={'rendering': policy})
        assert response.status_code == 200, response.text
        preview = response.json()['readiness']
        assert preview['parts'][0]['sounds'][0]['program'] == 3
        assert client.get('/api/queue').json() == before
        assert client.post(f'/api/library/assets/{asset}/performance/preview', json={}).json()['readiness']['parts'][0]['sounds'][0]['program'] == 41
        assert client.post('/api/library/assets/missing/performance/preview', json={}).status_code == 404
        assert client.post(f'/api/library/assets/{asset}/performance/preview', json={'rendering': {'mode': 'OVERRIDE', 'program_overrides': [{'channel': 9, 'program': 1}]}}).status_code == 422
        next((root / 'assets').glob('*.mid')).write_bytes(b'corrupt')
        failure = client.post(f'/api/library/assets/{asset}/performance/preview', json={})
        assert failure.status_code == 409
        assert failure.json()['error']['code'] == 'analysis_unavailable'


def test_facets_invalidate_favorites_wal_and_atomic_rebuild(tmp_path):
    root, _ = library(tmp_path)
    db = root / 'catalog.db'
    before = browse_facets(db)
    before['favorites'] = 999
    assert browse_facets(db)['favorites'] == 0
    with sqlite3.connect(db) as conn:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('UPDATE assets SET favorite=1')
        conn.commit()
        assert browse_facets(db)['favorites'] == 1
    conn.close()  # End the WAL connection before replacing its database file.
    rebuild_catalog(root)
    assert browse_facets(db)['favorites'] == 0


def test_automatic_preview_matches_resolved_orchestra_queue(tmp_path):
    from test_voicing_api import _client
    client, orchestra, _ = _client(tmp_path)
    with client:
        response = client.post(f'/api/library/assets/{orchestra}/performance/preview', json={})
        assert response.status_code == 200, response.text
        parts = response.json()['readiness']['parts']
        assert client.get('/api/queue').json()['items'] == []
        assert client.post('/api/queue', json={'asset_ids': [orchestra]}).status_code == 200
        policy = client.app.state.playback._queue[0].spec.rendering_policy
        assert policy is not None and policy.program_overrides
        expected = {o.channel + 1: o.program + 1 for o in policy.program_overrides}
        actual = {p['channel']: p['sounds'][0]['program'] for p in parts if p['changed']}
        assert actual == expected


def test_timeline_cache_retains_source_across_rendering_and_invalidates(tmp_path):
    path = tmp_path / 'song.mid'
    path.write_bytes(raw_midi([M('program_change', program=40), M('note_on', note=60)]))
    clock = ManualClock()
    engine = PlaybackEngine(router=MidiOutputRouter([VirtualMidiOutput('test', clock)]), history=None, clock=clock)
    first = engine._load_source(path)
    assert engine._load_source(path) is first
    render_timeline(first, RenderingPolicy.from_values(mode='PIANO_ONLY'))
    assert first.events[0].message.program == 40
    path.write_bytes(raw_midi([M('program_change', program=41), M('note_on', note=61)]))
    assert engine._load_source(path).events[0].message.program == 41


def test_fast_facts_agree_with_existing_mido_analysis(tmp_path):
    from openorchestrion.testing.midi_fixtures import generate_suite
    generate_suite(tmp_path)
    paths = list(tmp_path.rglob('*.mid'))
    assert paths
    for path in paths:
        midi = MidiFile(path)
        if midi.type == 2:
            continue
        facts = analyze_parts(path.read_bytes())
        existing = analyze_midifile(midi)
        assert sum(p['note_count'] for p in facts['parts']) == existing.note_count, path
        assert facts['peak_notes'] == existing.peak_simultaneous_notes, path
        assert facts['duration_seconds'] == pytest.approx(MidiTimeline.from_file(path).duration_seconds, abs=1e-5), path
