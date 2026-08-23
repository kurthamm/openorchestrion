"""Application wiring for hosted and offline Music Concierge providers."""

from __future__ import annotations

import os
from collections.abc import Mapping

from .ai import ConciergeResult, MusicConcierge, MusicConciergeProvider
from .api.settings import Settings
from .models import PlaybackIntent


def describe_intent(intent: PlaybackIntent) -> str:
    """Render validated intent as one readable appliance-facing sentence."""
    descriptors: list[str] = []
    if intent.familiarity == "high":
        descriptors.append("familiar")
    elif intent.familiarity == "low":
        descriptors.append("less familiar")

    if intent.energy == "high":
        descriptors.append("upbeat")
    elif intent.energy == "low":
        descriptors.append("relaxed")

    descriptors.extend(intent.moods[:2])
    descriptors.extend(intent.themes[:2])
    descriptors.extend(intent.genres[:2])
    descriptors.extend(intent.instrumentation[:2])

    if intent.performance_types and not intent.instrumentation:
        descriptors.append(intent.performance_types[0].value.replace("_", " ").casefold())

    # Preserve order while removing case-insensitive duplicates.
    seen: set[str] = set()
    unique: list[str] = []
    for value in descriptors:
        cleaned = str(value).strip()
        key = cleaned.casefold()
        if cleaned and key not in seen:
            seen.add(key)
            unique.append(cleaned)

    subject = " ".join(unique) if unique else "a varied selection"
    sentence = f"The request is for {subject} music"
    if intent.duration_minutes:
        sentence += f" for about {intent.duration_minutes} minutes"
    return (sentence + ".")[:500]


class ConfiguredMusicConcierge(MusicConcierge):
    """MusicConcierge that normalizes explanation and exposes safe status metadata."""

    def __init__(
        self,
        primary: MusicConciergeProvider | None = None,
        *,
        fallback: MusicConciergeProvider | None = None,
        configured_provider: str | None = None,
        unavailable_reason: str | None = None,
    ) -> None:
        super().__init__(primary=primary, fallback=fallback)
        self.configured_provider = configured_provider
        self.unavailable_reason = unavailable_reason

    async def interpret(
        self,
        prompt: str,
        *,
        current_intent: PlaybackIntent | None = None,
    ) -> ConciergeResult:
        result = await super().interpret(prompt, current_intent=current_intent)
        intent = result.intent.model_copy(deep=True)
        intent.interpretation = describe_intent(intent)

        configured_but_unavailable = self.configured_provider is not None and self.primary is None
        fallback_used = result.fallback_used or configured_but_unavailable
        primary_error = result.primary_error
        if configured_but_unavailable and primary_error is None:
            primary_error = self.unavailable_reason

        return ConciergeResult(
            intent=intent,
            provider=result.provider,
            fallback_used=fallback_used,
            primary_error=primary_error,
        )


def create_configured_concierge(
    settings: Settings,
    *,
    environ: Mapping[str, str] | None = None,
    openai_client: object | None = None,
) -> ConfiguredMusicConcierge:
    """Construct the configured provider without making hosted AI a boot dependency."""
    env = os.environ if environ is None else environ
    provider = settings.ai_provider
    if provider is None:
        return ConfiguredMusicConcierge(
            configured_provider=None,
            unavailable_reason="no_provider_configured_using_offline_interpreter",
        )

    if provider != "openai":
        return ConfiguredMusicConcierge(
            configured_provider=provider,
            unavailable_reason=f"unsupported_provider_{provider}_using_offline_interpreter",
        )

    api_key = env.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return ConfiguredMusicConcierge(
            configured_provider="openai",
            unavailable_reason="openai_api_key_missing_using_offline_interpreter",
        )

    try:
        from .ai_openai import create_openai_provider

        primary = create_openai_provider(
            api_key=api_key,
            model=settings.ai_model,
            timeout_seconds=settings.ai_timeout_seconds,
            client=openai_client,
        )
    except (ImportError, RuntimeError, ValueError) as exc:
        return ConfiguredMusicConcierge(
            configured_provider="openai",
            unavailable_reason=f"openai_unavailable_{type(exc).__name__}_using_offline_interpreter",
        )

    return ConfiguredMusicConcierge(
        primary=primary,
        configured_provider="openai",
        unavailable_reason=None,
    )


__all__ = ["ConfiguredMusicConcierge", "create_configured_concierge", "describe_intent"]
