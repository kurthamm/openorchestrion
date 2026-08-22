from pathlib import Path

from mido import Message, MetaMessage, MidiFile, MidiTrack, bpm2tempo

from openorchestrion.midi.analyzer import analyze_midi, analyze_midifile


def _base() -> MidiFile:
    midi = MidiFile(type=1, ticks_per_beat=480)
    conductor = MidiTrack()
    conductor.append(MetaMessage("set_tempo", tempo=bpm2tempo(120), time=0))
    conductor.append(MetaMessage("time_signature", numerator=4, denominator=4, time=0))
    midi.tracks.append(conductor)
    return midi


def test_gm_ensemble_analysis(tmp_path: Path) -> None:
    midi = _base()
    for name, channel, program, note in (
        ("piano", 0, 0, 60),
        ("bass", 1, 33, 36),
        ("strings", 2, 48, 55),
        ("trumpet", 3, 56, 67),
        ("sax", 4, 65, 64),
    ):
        track = MidiTrack()
        track.append(MetaMessage("track_name", name=name, time=0))
        track.append(Message("program_change", channel=channel, program=program, time=0))
        track.append(Message("note_on", channel=channel, note=note, velocity=88, time=0))
        track.append(Message("note_off", channel=channel, note=note, velocity=0, time=480))
        midi.tracks.append(track)

    drums = MidiTrack()
    drums.append(MetaMessage("track_name", name="drums", time=0))
    drums.append(Message("note_on", channel=9, note=36, velocity=100, time=0))
    drums.append(Message("note_off", channel=9, note=36, velocity=0, time=480))
    midi.tracks.append(drums)

    path = tmp_path / "ensemble.mid"
    midi.save(path)
    analysis = analyze_midi(path)

    assert analysis.channels == [1, 2, 3, 4, 5, 10]
    assert analysis.percussion_channels == [10]
    assert analysis.percussion_note_count == 1
    assert analysis.peak_simultaneous_notes == 6
    assert analysis.assessment["gm_assessment"] == "gm-compatible-structure"
    assert [program.gm_program_number for program in analysis.program_uses] == [1, 34, 49, 57, 66]
    assert analysis.sha256 is not None and len(analysis.sha256) == 64


def test_sustain_extends_estimated_voice_lifetime() -> None:
    midi = _base()
    track = MidiTrack()
    track.append(Message("control_change", channel=0, control=64, value=127, time=0))
    track.append(Message("note_on", channel=0, note=60, velocity=90, time=0))
    track.append(Message("note_off", channel=0, note=60, velocity=0, time=240))
    track.append(Message("note_on", channel=0, note=64, velocity=90, time=0))
    track.append(Message("note_off", channel=0, note=64, velocity=0, time=240))
    track.append(Message("control_change", channel=0, control=64, value=0, time=240))
    midi.tracks.append(track)

    analysis = analyze_midifile(midi)
    assert analysis.sustain_used is True
    assert analysis.peak_simultaneous_notes == 2
    sustain = next(control for control in analysis.controllers if control.controller == 64)
    assert sustain.values == [0, 127]


def test_velocity_and_note_range() -> None:
    midi = _base()
    track = MidiTrack()
    for note, velocity in ((0, 20), (60, 70), (127, 120)):
        track.append(Message("note_on", channel=0, note=note, velocity=velocity, time=0))
        track.append(Message("note_off", channel=0, note=note, velocity=0, time=120))
    midi.tracks.append(track)

    analysis = analyze_midifile(midi)
    assert analysis.note_min == 0
    assert analysis.note_max == 127
    assert analysis.velocity.minimum == 20
    assert analysis.velocity.maximum == 120
    assert analysis.velocity.mean == 70.0
    assert analysis.assessment["full_midi_note_range_exercised"] is True


def test_program_change_captures_bank_select() -> None:
    midi = _base()
    track = MidiTrack()
    track.append(Message("control_change", channel=0, control=0, value=12, time=0))
    track.append(Message("control_change", channel=0, control=32, value=3, time=0))
    track.append(Message("program_change", channel=0, program=48, time=0))
    midi.tracks.append(track)

    analysis = analyze_midifile(midi)
    assert analysis.program_uses[0].bank_msb == 12
    assert analysis.program_uses[0].bank_lsb == 3
    assert analysis.assessment["gm_assessment"] == "extended-or-device-specific-bank"


def test_expressive_and_sysex_flags() -> None:
    midi = _base()
    track = MidiTrack()
    track.append(Message("pitchwheel", channel=0, pitch=100, time=0))
    track.append(Message("aftertouch", channel=0, value=20, time=0))
    track.append(Message("polytouch", channel=0, note=60, value=30, time=0))
    track.append(Message("sysex", data=(0x7E, 0x7F, 0x09, 0x01), time=0))
    midi.tracks.append(track)

    analysis = analyze_midifile(midi)
    assert analysis.pitch_bend_used
    assert analysis.channel_aftertouch_used
    assert analysis.poly_aftertouch_used
    assert analysis.sysex_count == 1
    assert analysis.assessment["uses_sysex"] is True
