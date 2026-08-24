from __future__ import annotations

import pytest

from openorchestrion.midi.gm import (
    GM_PROGRAM_NAMES,
    GMProgramError,
    gm_program_name,
    resolve_gm_program,
)


def test_general_midi_table_has_exactly_128_unique_program_names() -> None:
    assert len(GM_PROGRAM_NAMES) == 128
    assert len(set(GM_PROGRAM_NAMES)) == 128


@pytest.mark.parametrize(
    "value, expected",
    [
        (0, 0),
        (127, 127),
        ("Acoustic Grand Piano", 0),
        ("acoustic grand piano", 0),
        ("HONKY TONK PIANO", 3),
        ("Acoustic Guitar nylon", 24),
        ("Violin", 40),
        ("lead 8 bass + lead", 87),
        ("FX 8 sci-fi", 103),
        ("piano", 0),
        ("grand piano", 0),
    ],
)
def test_resolve_gm_program_accepts_internal_numbers_and_names(
    value: int | str,
    expected: int,
) -> None:
    assert resolve_gm_program(value) == expected


@pytest.mark.parametrize("value", [-1, 128, True])
def test_invalid_internal_program_numbers_are_rejected(value: int) -> None:
    with pytest.raises(GMProgramError):
        resolve_gm_program(value)


@pytest.mark.parametrize("value", ["", "   ", "0", "1", "128"])
def test_numeric_and_blank_strings_are_rejected_as_ambiguous(value: str) -> None:
    with pytest.raises(GMProgramError):
        resolve_gm_program(value)


@pytest.mark.parametrize("value", ["strings", "organ", "electric piano", "not a patch"])
def test_ambiguous_family_or_unknown_names_are_rejected(value: str) -> None:
    with pytest.raises(GMProgramError, match="unknown or ambiguous"):
        resolve_gm_program(value)


def test_program_name_round_trip_uses_midi_native_numbering() -> None:
    for number, name in enumerate(GM_PROGRAM_NAMES):
        assert resolve_gm_program(name) == number
        assert gm_program_name(number) == name
