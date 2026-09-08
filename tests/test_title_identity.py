import hashlib
import json

import pytest

from openorchestrion.library.title_identity import decode_label, source_identity
from openorchestrion.library.title_repair import proposal, make_plan, execute_plan
from openorchestrion.library.metadata import update_metadata, read_metadata, read_csv_edits
from openorchestrion.library.importer import import_paths
from openorchestrion.library.catalog import rebuild_catalog, get_asset
from openorchestrion.library.browse import browse
from openorchestrion.testing.midi_fixtures import generate_suite


@pytest.mark.parametrize('source,expected', [
    ('%C9tude', 'Étude'), ('Vogel im K%E4fig', 'Vogel im Käfig'),
    ('%E3%81%95', 'さ'), ('&#12373;&#12424;&#12394;&#12425;&#12398;&#22799;', 'さよならの夏'),
    ('A &amp; B', 'A & B'), ('Andre\u0301', 'André'), ('AC+DC', 'AC+DC'),
    ('100% live', '100% live'), ('A &not a name', 'A &not a name'),
    ('%00', '%00'), ('%81', '%81'), ('  A\t B ', 'A B'),
])
def test_decode_without_replacement_characters(source, expected):
    assert decode_label(source) == expected
    assert decode_label(expected) == expected


def test_slug_punctuation_and_context():
    result = source_identity("John Lee Hooker - (The-Blues-Is)-The-Healer-1.mid", source='BitMidi')
    assert result['title'] == '(The Blues Is) The Healer [1]'
    assert result['source_context'] == 'John Lee Hooker'
    assert result['source_title'].endswith('.mid')
    assert 'artist' not in result
    for value in ('1-2-3', 'B-52', 'Jean-Michel', 'Saint-Saëns'):
        assert source_identity(value, source='BitMidi')['title'] == value
    assert source_identity('Ob-La-Di-Ob-La-Da', source='BitMidi')['title'] == 'Ob-La-Di Ob-La-Da'
    assert source_identity('ABBA.Take a chance on me K.mid', source='BitMidi')['source_context'] == 'ABBA'
    assert source_identity('051230', source='BitMidi')['title_status'] == 'unresolved'


def test_dont_replace_curated_identity_or_mistake_game_for_composer():
    doc = {'provenance': {'source_label': 'BitMidi', 'attribution': "BitMidi upload 'Naruto - A-Theme-Song.mid' (original sequencer unknown)"},
           'descriptive_metadata': {'title': 'A-Theme-Song', 'composer': 'Naruto', 'favorite': True}}
    repaired = proposal(doc)
    assert repaired['source_context'] == 'Naruto' and 'composer' not in repaired
    assert repaired['favorite']
    doc['descriptive_metadata']['title'] = 'A separately verified title'
    assert proposal(doc) == doc['descriptive_metadata']


def test_csv_decodes_but_preserves_original(tmp_path):
    path = tmp_path / 'tags.csv'
    path.write_text('sha256,title\n' + 'a'*64 + ',%C9tude\n')
    edit = read_csv_edits(path)[0][1]
    assert edit == {'title': 'Étude', 'source_title': '%C9tude'}


def test_source_download_bytes_and_display_decoding_are_separate():
    from openorchestrion.library.acquisition_sources import Source, checked_url, page_links
    source = Source('test', 'Test', (), ('example.org',), ('/music/',), 'classical')
    url = 'https://example.org/music/%C9tude.mid'
    assert checked_url(source, url) == url
    result = page_links(source, 'https://example.org/music/', b'<a href="%C9tude.mid">MIDI</a>')
    assert result[0]['title'] == 'Étude' and result[0]['url'] == url
    with pytest.raises(ValueError, match='unsafe'):
        checked_url(source, 'https://example.org/music/%2e%2e/private.mid')


def test_migration_search_preservation_conflicts_and_rollback(tmp_path):
    fixtures, root = tmp_path/'fixtures', tmp_path/'library'
    generate_suite(fixtures, long_run_minutes=1)
    import_paths([fixtures], root)
    rebuild_catalog(root)
    sidecar = next((root/'assets').glob('*.json'))
    doc = json.loads(sidecar.read_bytes())
    doc['provenance'].update(source_label='BitMidi', attribution="BitMidi upload 'Clannad - %C9tude.mid' (original sequencer unknown)")
    doc['descriptive_metadata'] = {'title':'%C9tude', 'artist':'Clannad', 'favorite':True}
    sidecar.write_text(json.dumps(doc))
    rebuild_catalog(root)
    midi = sidecar.with_suffix('.mid')
    digest = hashlib.sha256(midi.read_bytes()).hexdigest()
    plan = make_plan(root)
    entry = next(e for e in plan['entries'] if e['asset_id']==doc['asset_id'])
    update_metadata(root, doc['asset_id'], {'favorite':False})
    with pytest.raises(ValueError, match='changed'):
        execute_plan(root, plan)
    assert read_metadata(root, doc['asset_id']).descriptive_metadata['title']=='%C9tude'
    # New plan accepts the user's favorite edit and preserves it through both directions.
    plan = make_plan(root)
    execute_plan(root, plan)
    assert browse(root/'catalog.db', text='Clannad Etude')['total']==1
    assert browse(root/'catalog.db', text='%C9tude')['total']==1
    item = get_asset(root/'catalog.db', doc['asset_id'])
    assert item['title']=='Étude' and item['source_context']=='Clannad'
    assert item['artist'] is None and not item['favorite']
    assert execute_plan(root, plan)['changed']==0
    execute_plan(root, plan, rollback=True)
    assert get_asset(root/'catalog.db', doc['asset_id'])['title']=='%C9tude'
    assert hashlib.sha256(midi.read_bytes()).hexdigest()==digest
    restored = json.loads(sidecar.read_bytes())
    for field in ('provenance','deterministic_analysis','file','ai_enrichment'):
        assert restored[field]==doc[field]
    assert entry['before']['favorite']
