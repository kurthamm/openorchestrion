from __future__ import annotations

from openorchestrion.playback.voicing import looks_orchestral, suggest_program_overrides


def _analysis(parts, *, names=None):
    """parts: {midi channel 0..15: program}; names: {channel: track name}.

    The stored analysis numbers channels 1..16, so the helper adds one the way
    the analyzer does; the suggestions come back MIDI-native like the tests.
    """
    names = names or {}
    return {
        "melodic_channels": [ch + 1 for ch in sorted(parts)],
        "program_uses": [
            {"tick": 0, "channel": ch + 1, "program_zero_based": prog} for ch, prog in parts.items() if prog is not None
        ],
        "tracks": [
            {"index": i, "name": names.get(ch, f"track {i}"), "channels": [ch + 1], "note_count": 100}
            for i, ch in enumerate(sorted(parts))
        ],
    }


BEETHOVEN_7 = {1: 73, 2: 68, 3: 71, 4: 70, 5: 69, 6: 69, 7: 47, 8: 40, 10: 40, 11: 41, 12: 42, 13: 43}


def test_orchestral_score_with_solo_string_sections_is_re_voiced() -> None:
    analysis = _analysis(BEETHOVEN_7, names={5: "corno 1", 6: "corno 2"})
    assert looks_orchestral(analysis)
    assert suggest_program_overrides(analysis) == (
        (5, 60),  # horn parts on English Horn -> French Horn
        (6, 60),
        (8, 48),  # solo string patches on section parts -> String Ensemble
        (10, 48),
        (11, 48),
        (12, 48),
        (13, 48),
    )


def test_english_horn_stays_when_the_part_really_is_one() -> None:
    parts = dict(BEETHOVEN_7)
    analysis = _analysis(parts, names={5: "English Horn", 6: "Cor anglais"})
    overrides = dict(suggest_program_overrides(analysis))
    assert 5 not in overrides and 6 not in overrides


def test_string_quartet_keeps_its_solo_strings() -> None:
    analysis = _analysis({0: 40, 1: 40, 2: 41, 3: 42})
    assert not looks_orchestral(analysis)
    assert suggest_program_overrides(analysis) == ()


def test_solo_piano_and_piano_duet_are_untouched() -> None:
    assert suggest_program_overrides(_analysis({0: 0, 1: 0})) == ()
    assert suggest_program_overrides(_analysis({0: None, 1: None})) == ()


def test_orchestra_exported_without_program_changes_is_voiced_from_part_names() -> None:
    names = {0: "Flauto", 1: "Oboe", 2: "Clarinetto in A", 3: "Fagotto", 4: "Corni in E", 5: "Trombe", 6: "Timpani",
             7: "Violino I", 8: "Violino II", 10: "Viola", 11: "Violoncello", 12: "Contrabasso"}
    analysis = _analysis({ch: None for ch in names}, names=names)
    assert looks_orchestral(analysis)
    assert suggest_program_overrides(analysis) == (
        (0, 73), (1, 68), (2, 71), (3, 70), (4, 60), (5, 56), (6, 47),
        (7, 48), (8, 48), (10, 48), (11, 48), (12, 48),
    )


def test_percussion_channel_is_never_overridden() -> None:
    parts = dict(BEETHOVEN_7)
    parts[9] = 0
    analysis = _analysis(parts, names={9: "Timpani"})
    assert 9 not in dict(suggest_program_overrides(analysis))


def test_correct_programs_produce_no_override() -> None:
    parts = {0: 73, 1: 68, 2: 71, 3: 70, 4: 60, 5: 56, 6: 47, 7: 48, 8: 48}
    assert suggest_program_overrides(_analysis(parts)) == ()


def test_auto_preserves_program_changes_and_nonzero_banks() -> None:
    analysis = _analysis(BEETHOVEN_7)
    analysis["program_uses"].append({"tick": 480, "channel": 9, "program_zero_based": 45})
    for use in analysis["program_uses"]:
        if use["channel"] == 11:
            use["bank_msb"] = 1
    overrides = dict(suggest_program_overrides(analysis))
    assert 8 not in overrides
    assert 10 not in overrides
    assert overrides[11] == 48
