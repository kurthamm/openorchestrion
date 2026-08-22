from __future__ import annotations

import pytest

from openorchestrion.ai import (
    CallableIntentBackend,
    ConciergeSession,
    DeterministicConciergeProvider,
    MusicConcierge,
    ProviderOutputError,
    ValidatingJSONConciergeProvider,
)
from openorchestrion.models import PerformanceType, PlaybackIntent


@pytest.mark.asyncio
async def test_dinner_music_two_hours() -> None:
    provider = DeterministicConciergeProvider()
    intent = await provider.interpret("Play dinner music for about two hours")

    assert "dinner" in intent.themes
    assert intent.duration_minutes == 120
    assert intent.continuation_behavior == "replace"


@pytest.mark.asyncio
async def test_popular_christmas_music() -> None:
    provider = DeterministicConciergeProvider()
    intent = await provider.interpret("Play popular Christmas music")

    assert "Christmas" in intent.themes
    assert intent.familiarity == "high"


@pytest.mark.asyncio
async def test_relaxing_classical_piano() -> None:
    provider = DeterministicConciergeProvider()
    intent = await provider.interpret("Give me relaxing classical piano")

    assert "classical" in intent.genres
    assert "relaxed" in intent.moods
    assert "piano" in intent.instrumentation
    assert intent.energy == "low"


@pytest.mark.asyncio
async def test_conversational_refinement_preserves_context() -> None:
    session = ConciergeSession()

    await session.ask("Play dinner music for two hours")
    await session.ask("A little more upbeat")
    await session.ask("More recognizable")
    await session.ask("Add Christmas music")
    result = await session.ask("More piano")

    intent = result.intent
    assert intent.duration_minutes == 120
    assert "dinner" in intent.themes
    assert "Christmas" in intent.themes
    assert "piano" in intent.instrumentation
    assert intent.energy == "medium"
    assert intent.familiarity == "high"
    assert intent.continuation_behavior == "refine"


@pytest.mark.asyncio
async def test_dueling_pianos_request() -> None:
    provider = DeterministicConciergeProvider()
    intent = await provider.interpret("Give me dueling pianos for an hour")

    assert intent.duration_minutes == 60
    assert intent.performance_types == [PerformanceType.DUELING_PIANO]
    assert "piano" in intent.instrumentation


@pytest.mark.asyncio
async def test_orchestral_refinement_replaces_solo_piano_preference() -> None:
    provider = DeterministicConciergeProvider()
    current = await provider.interpret("Popular Christmas solo piano")
    intent = await provider.interpret(
        "But orchestral instead of solo piano",
        current_intent=current,
    )

    assert "Christmas" in intent.themes
    assert "orchestra" in intent.instrumentation
    assert "piano" not in {value.casefold() for value in intent.instrumentation}
    assert intent.performance_types == [PerformanceType.MULTI_INSTRUMENT]


@pytest.mark.asyncio
async def test_structured_provider_rejects_unknown_fields() -> None:
    async def callback(**_: object) -> dict[str, object]:
        return {"mode": "station", "sysex": "F0 7E 7F 09 01 F7"}

    provider = ValidatingJSONConciergeProvider(CallableIntentBackend(callback))

    with pytest.raises(ProviderOutputError):
        await provider.interpret("Play something")


@pytest.mark.asyncio
async def test_structured_provider_must_preserve_hard_exclusions_on_refinement() -> None:
    current = PlaybackIntent(
        themes=["dinner"],
        exclude_tags=["dramatic"],
        energy="low",
    )

    async def callback(**_: object) -> dict[str, object]:
        payload = current.model_dump(mode="json")
        payload["energy"] = "medium"
        payload["exclude_tags"] = []
        return payload

    provider = ValidatingJSONConciergeProvider(CallableIntentBackend(callback))

    with pytest.raises(ProviderOutputError, match="hard exclude"):
        await provider.interpret("More upbeat", current_intent=current)


@pytest.mark.asyncio
async def test_provider_failure_falls_back_to_local_interpreter() -> None:
    async def callback(**_: object) -> dict[str, object]:
        raise RuntimeError("provider unavailable")

    primary = ValidatingJSONConciergeProvider(
        CallableIntentBackend(callback),
        name="test-hosted-provider",
    )
    concierge = MusicConcierge(primary=primary)
    result = await concierge.interpret("Play popular Christmas music")

    assert result.fallback_used is True
    assert result.provider == "deterministic-fallback"
    assert result.primary_error is not None
    assert "Christmas" in result.intent.themes
    assert result.intent.familiarity == "high"


def test_playback_intent_forbids_model_hallucinated_fields() -> None:
    with pytest.raises(ValueError):
        PlaybackIntent.model_validate({"mode": "station", "midi_command": "note_on"})
