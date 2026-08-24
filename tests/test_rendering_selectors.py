from __future__ import annotations

import pytest

from openorchestrion.playback import ProgramOverride, RenderingError, RenderingMode, RenderingPolicy


def test_program_override_resolves_canonical_gm_name() -> None:
    override = ProgramOverride.from_value(0, "Violin")

    assert override.channel == 0
    assert override.program == 40


def test_program_override_resolves_punctuation_and_case_variants() -> None:
    assert ProgramOverride.from_value(2, "acoustic guitar nylon").program == 24
    assert ProgramOverride.from_value(3, "HONKY TONK PIANO").program == 3


def test_policy_from_values_resolves_mode_piano_and_overrides() -> None:
    policy = RenderingPolicy.from_values(
        mode="PIANO_ONLY",
        piano_program="Honky-tonk Piano",
        program_overrides=((1, "Violin"), (2, 24)),
    )

    assert policy.mode is RenderingMode.PIANO_ONLY
    assert policy.piano_program == 3
    assert policy.program_overrides == (
        ProgramOverride(channel=1, program=40),
        ProgramOverride(channel=2, program=24),
    )


def test_request_friendly_builder_preserves_duplicate_channel_rejection() -> None:
    with pytest.raises(RenderingError, match="one program override"):
        RenderingPolicy.from_values(
            mode="OVERRIDE",
            program_overrides=((0, "Violin"), (0, "Flute")),
        )


@pytest.mark.parametrize(
    "program, message",
    [
        ("strings", "unknown or ambiguous"),
        ("1", "numeric strings are ambiguous"),
        ("not a patch", "unknown or ambiguous"),
    ],
)
def test_named_override_failures_are_rendering_errors(program: str, message: str) -> None:
    with pytest.raises(RenderingError, match=message):
        ProgramOverride.from_value(0, program)


def test_piano_program_name_must_still_be_from_gm_piano_family() -> None:
    with pytest.raises(RenderingError, match="piano_program"):
        RenderingPolicy.from_values(mode="PIANO_ONLY", piano_program="Violin")


def test_invalid_rendering_mode_fails_at_domain_boundary() -> None:
    with pytest.raises(RenderingError, match="rendering mode must be one of"):
        RenderingPolicy.from_values(mode="MAKE_IT_WEIRD")
