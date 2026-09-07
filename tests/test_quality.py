import io

from mido import Message, MidiFile, MidiTrack

from openorchestrion.library.quality import analyze, decide


def midi(messages):
    file = MidiFile()
    file.tracks = [MidiTrack(messages)]
    out = io.BytesIO()
    file.save(file=out)
    return out.getvalue()


def test_sostenuto_only_holds_notes_present_at_pedal_down():
    facts = analyze(
        midi(
            [
                Message("note_on", note=60),
                Message("control_change", control=66, value=127),
                Message("note_on", note=64),
                Message("note_off", note=60, time=480),
                Message("note_off", note=64),
            ]
        )
    )
    assert facts["parts"][0]["pedal_held_at_end"] == 1
    assert facts["parts"][0]["unreleased_keys"] == 0
    assert facts["peak_pitched_notes"] == 2


def test_sustain_and_sostenuto_release_independently():
    facts = analyze(
        midi(
            [
                Message("note_on", note=60),
                Message("control_change", control=66, value=127),
                Message("control_change", control=64, value=127),
                Message("note_off", note=60, time=480),
                Message("control_change", control=66, value=0),
                Message("control_change", control=64, value=0),
            ]
        )
    )
    assert facts["parts"][0]["pedal_held_at_end"] == 0


def test_all_notes_off_respects_sustain_and_all_sound_off_clears_keys():
    facts = analyze(
        midi(
            [
                Message("control_change", control=64, value=127),
                Message("note_on", note=60),
                Message("control_change", control=123, value=0),
                Message("control_change", control=120, value=0),
            ]
        )
    )
    assert facts["parts"][0]["unreleased_keys"] == 0
    assert facts["parts"][0]["pedal_held_at_end"] == 0


def test_metadata_or_source_name_alone_never_certifies_completeness():
    facts = analyze(midi([Message("note_on", note=60), Message("note_off", note=60, time=480)]))
    entry = {"asset_id": "example", "provenance": {"source_label": "MAESTRO"}, "facts": facts}
    assert "completeness_unresolved" in decide(entry)["reasons"]
    proof = {"example": {"completeness": "complete", "performance_capture": True}}
    assert decide(entry, proof)["status"] == "qualified"
    assert decide(entry, {"example": {"completeness": "partial"}})["status"] == "excluded"


def test_verified_source_still_fails_unreleased_notes_and_unknown_bank():
    facts = analyze(
        midi(
            [
                Message("control_change", control=32, value=2),
                Message("program_change", program=0),
                Message("note_on", note=60),
            ]
        )
    )
    result = decide(
        {"asset_id": "a", "facts": facts},
        {"a": {"completeness": "complete", "performance_capture": True}},
    )
    assert result["status"] == "unresolved"
    assert "unresolved_note_endings" in result["reasons"]
    assert "unverified_sound_bank" in result["warnings"]


def test_expression_requires_changes_not_repeated_initialization():
    messages = [Message("program_change", program=0)]
    for _ in range(40):
        messages.extend(
            [
                Message("control_change", control=11, value=100),
                Message("note_on", note=60, velocity=80),
                Message("note_off", note=60, time=48),
            ]
        )
    entry = {"asset_id": "a", "facts": analyze(midi(messages))}
    result = decide(entry, {"a": {"completeness": "complete"}})
    assert "insufficient_performance_expression" in result["reasons"]
