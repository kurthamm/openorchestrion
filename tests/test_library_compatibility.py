from copy import deepcopy

from mido import Message as M

from openorchestrion.library.compatibility import sound_palette
from openorchestrion.library.readiness import analyze_parts, readiness
from openorchestrion.playback.rendering import RenderingPolicy
from test_playback_readiness import raw_midi


def test_explicit_piano_is_not_confused_with_missing_instrument_assignment():
    implicit = analyze_parts(raw_midi([M('note_on', note=60)]))
    explicit = analyze_parts(raw_midi([M('program_change', program=0), M('note_on', note=60)]))
    assert sound_palette(implicit['parts'])['kind'] == 'piano_default'
    assert sound_palette(explicit['parts'])['kind'] == 'acoustic_piano'
    # Multiple MIDI channels do not imply multiple musicians or instruments.
    parts = deepcopy(explicit['parts']) * 2
    assert sound_palette(parts)['kind'] == 'acoustic_piano'
    assert sound_palette(parts)['sounding_channels'] == 2


def test_sequential_sounds_on_one_channel_are_multiple_instruments():
    facts = analyze_parts(raw_midi([M('program_change', program=40), M('note_on', note=60),
                                   M('program_change', program=73), M('note_on', note=62)]))
    assert sound_palette(facts['parts']) == {
        'kind': 'multiple_instruments', 'label': 'Multiple instrument sounds',
        'sounding_channels': 1, 'pitched_sound_count': 2, 'percussion': False,
    }


def test_lsb_limitation_is_specific_and_does_not_rewrite_source_banks():
    facts = analyze_parts(raw_midi([M('control_change', control=32, value=2),
                                   M('program_change', program=0), M('note_on', note=60)]))
    original = deepcopy(facts)
    preview = readiness(facts, 'MULTI_INSTRUMENT')
    sound = preview['parts'][0]['sounds'][0]
    assert sound['mapping_status'] == 'gm_baseline'
    assert 'ignores bank LSB 2' in sound['mapping_note']
    assert sound['bank_lsb'] == 2
    flags = {f['code'] for f in preview['flags']}
    assert 'wk220_bank_lsb_ignored' in flags
    assert 'unverified_sound_mapping' not in flags
    assert preview['source_palette']['kind'] == 'device_dependent'
    assert facts == original
    piano = readiness(facts, None, RenderingPolicy.from_values(mode='PIANO_ONLY'))
    assert piano['source_palette']['kind'] == 'device_dependent'
    assert piano['playback_palette']['kind'] == 'acoustic_piano'
    assert 'wk220_bank_lsb_ignored' not in {f['code'] for f in piano['flags']}


def test_unverified_vendor_bank_and_drum_kit_remain_unverified():
    facts = analyze_parts(raw_midi([M('control_change', control=0, value=56),
                                   M('program_change', program=0), M('note_on', note=60),
                                   M('program_change', channel=9, program=16),
                                   M('note_on', channel=9, note=36)]))
    preview = readiness(facts, None)
    assert all(p['sounds'][0]['mapping_status'] == 'unverified' for p in preview['parts'])
    assert 'unverified_sound_mapping' in {f['code'] for f in preview['flags']}


def test_drum_only_and_empty_source_do_not_become_piano_arrangements():
    facts = analyze_parts(raw_midi([M('note_on', channel=9, note=36)]))
    preview = readiness(facts, None, RenderingPolicy.from_values(mode='PIANO_ONLY'))
    assert preview['source_palette']['kind'] == 'percussion_only'
    assert preview['playback_palette']['kind'] == 'silent'
    assert preview['status'] == 'caution'
