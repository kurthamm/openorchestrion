from openorchestrion.midi.analyzer import analyze_midifile
from openorchestrion.testing.midi_fixtures import (
    gm_ensemble,
    note_range,
    polyphony_stress,
    sustain_cc64,
    two_piano_split,
)


def test_generated_gm_ensemble_matches_analyzer_expectations() -> None:
    analysis = analyze_midifile(gm_ensemble(), source="gm-ensemble.mid")
    assert analysis.channels == [1, 2, 3, 4, 5, 10]
    assert analysis.note_count == 28
    assert analysis.percussion_note_count == 8
    assert analysis.peak_simultaneous_notes == 6
    assert analysis.assessment["gm_assessment"] == "gm-compatible-structure"


def test_generated_note_range_exercises_full_midi_range() -> None:
    analysis = analyze_midifile(note_range(), source="note-range.mid")
    assert analysis.note_min == 0
    assert analysis.note_max == 127
    assert analysis.assessment["full_midi_note_range_exercised"] is True


def test_generated_polyphony_fixture_reports_requested_peak() -> None:
    analysis = analyze_midifile(polyphony_stress(48), source="polyphony-48.mid")
    assert analysis.peak_simultaneous_notes == 48
    assert analysis.assessment["peak_over_32"] is True
    assert analysis.assessment["peak_over_48"] is False


def test_generated_sustain_and_two_piano_structure() -> None:
    sustain = analyze_midifile(sustain_cc64(), source="sustain-cc64.mid")
    duet = analyze_midifile(two_piano_split(), source="two-piano-split.mid")
    assert sustain.sustain_used is True
    assert duet.channels == [1, 2]
    assert [track.name for track in duet.tracks if track.note_count] == [
        "Piano I / Device A",
        "Piano II / Device B",
    ]
