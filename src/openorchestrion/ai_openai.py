"""OpenAI adapter for the provider-neutral Music Concierge.

The import of the OpenAI SDK is deliberately lazy. Offline appliances neither
need nor install it, and merely importing :mod:`openorchestrion` must never make
a hosted-provider dependency mandatory.

The public :class:`PlaybackIntent` intentionally contains a free-form
``routing_preferences`` mapping and friendly defaults. OpenAI Structured Outputs
requires closed objects and every field to be required, so this module uses a
strict provider-only transport model and converts it back to ``PlaybackIntent``.
That keeps the public application contract unchanged while making the hosted
boundary compatible with strict structured output.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .ai import ProviderOutputError, ValidatingJSONConciergeProvider
from .models import PerformanceType, PlaybackIntent

DEFAULT_OPENAI_MODEL = "gpt-5.6-luna"
DEFAULT_OPENAI_TIMEOUT_SECONDS = 15.0


class OpenAIRoutingPreference(BaseModel):
    """One entry from PlaybackIntent.routing_preferences in strict-schema form."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1)
    value: str = Field(min_length=1)


class OpenAIPlaybackIntent(BaseModel):
    """Strict Responses-API transport schema for the public PlaybackIntent.

    Every field is intentionally required. Domain fields that are optional are
    nullable rather than omitted, and the free-form routing mapping becomes a
    list of closed key/value objects so no schema object needs arbitrary
    ``additionalProperties``.
    """

    model_config = ConfigDict(extra="forbid")

    mode: Literal["station", "queue", "single", "modify_current"]
    duration_minutes: int | None = Field(ge=1, le=1440)
    genres: list[str]
    moods: list[str]
    themes: list[str]
    eras: list[str]
    composers: list[str]
    artists: list[str]
    instrumentation: list[str]
    performance_types: list[PerformanceType]
    familiarity: Literal["low", "medium", "high"] | None
    energy: Literal["low", "medium", "high"] | None
    tempo_preference: Literal["slow", "medium", "fast", "mixed"] | None
    include_tags: list[str]
    exclude_tags: list[str]
    avoid_recent_repeats: bool
    repeat_window_days: int | None = Field(ge=0, le=3650)
    device_preferences: list[str]
    routing_preferences: list[OpenAIRoutingPreference]
    continuation_behavior: Literal["replace", "refine", "append"] | None
    interpretation: str | None = Field(max_length=500)

    @model_validator(mode="after")
    def _unique_routing_keys(self) -> OpenAIPlaybackIntent:
        keys = [entry.key for entry in self.routing_preferences]
        if len(keys) != len(set(keys)):
            raise ValueError("routing preference keys must be unique")
        return self

    @classmethod
    def from_playback_intent(cls, intent: PlaybackIntent) -> OpenAIPlaybackIntent:
        payload = intent.model_dump(mode="python")
        routing = payload.pop("routing_preferences")
        payload["routing_preferences"] = [
            {"key": key, "value": value} for key, value in routing.items()
        ]
        return cls.model_validate(payload)

    def to_playback_intent(self) -> PlaybackIntent:
        payload = self.model_dump(mode="json")
        routing = payload.pop("routing_preferences")
        payload["routing_preferences"] = {
            entry["key"]: entry["value"] for entry in routing
        }
        return PlaybackIntent.model_validate(payload)


class OpenAIIntentBackend:
    """Interpret prompts with Responses API structured outputs.

    ``client`` is injectable so the complete adapter is testable without a live
    API key or network. With no injected client, the current OpenAI Python SDK is
    imported and an ``AsyncOpenAI`` client is created.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = DEFAULT_OPENAI_MODEL,
        timeout_seconds: float = DEFAULT_OPENAI_TIMEOUT_SECONDS,
        client: Any | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("OpenAI timeout must be positive")
        self.model = model.strip() or DEFAULT_OPENAI_MODEL
        self.timeout_seconds = float(timeout_seconds)

        if client is None:
            try:
                from openai import AsyncOpenAI
            except ImportError as exc:  # pragma: no cover - exercised through factory
                raise RuntimeError(
                    "OpenAI provider requested but the optional OpenAI SDK is not installed"
                ) from exc
            if not api_key:
                raise RuntimeError("OpenAI provider requested but OPENAI_API_KEY is not configured")
            client = AsyncOpenAI(api_key=api_key, timeout=self.timeout_seconds)
        self.client = client

    async def generate_intent(
        self,
        *,
        prompt: str,
        current_intent: Mapping[str, Any] | None,
        contract: str,
    ) -> Mapping[str, Any]:
        if current_intent is None:
            context = "There is no current intent. Treat this as a replacement request."
        else:
            domain_intent = PlaybackIntent.model_validate(dict(current_intent))
            transport_intent = OpenAIPlaybackIntent.from_playback_intent(domain_intent)
            context = (
                "Current validated intent JSON follows. Return the complete merged intent, "
                "preserving unrelated preferences and hard include/exclude tags when this is "
                "a refinement. In this provider schema routing_preferences is represented as "
                "a list of {key, value} entries:\n"
                + json.dumps(transport_intent.model_dump(mode="json"), sort_keys=True)
            )
        user_text = f"{context}\n\nUser music request:\n{prompt}"
        instructions = (
            contract
            + "\nFor this provider's strict schema, routing_preferences is an array of "
            "objects with required key and value strings. It maps losslessly to the "
            "application's routing_preferences object after validation."
        )

        response = await self.client.responses.parse(
            model=self.model,
            instructions=instructions,
            input=[{"role": "user", "content": user_text}],
            text_format=OpenAIPlaybackIntent,
        )

        refusal = _refusal_text(response)
        if refusal:
            raise ProviderOutputError(f"OpenAI refused the request: {refusal}")

        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            raise ProviderOutputError("OpenAI returned no parsed intent")
        if not isinstance(parsed, OpenAIPlaybackIntent):
            try:
                parsed = OpenAIPlaybackIntent.model_validate(parsed)
            except Exception as exc:  # noqa: BLE001 - provider boundary
                raise ProviderOutputError("OpenAI parsed output was not a valid intent") from exc
        return parsed.to_playback_intent().model_dump(mode="json")


def _refusal_text(response: Any) -> str | None:
    """Return a provider refusal without depending on SDK-private response types."""
    parts: list[str] = []
    for output in getattr(response, "output", ()) or ():
        if getattr(output, "type", None) != "message":
            continue
        for item in getattr(output, "content", ()) or ():
            if getattr(item, "type", None) != "refusal":
                continue
            value = getattr(item, "refusal", None) or getattr(item, "text", None)
            if value:
                parts.append(str(value))
    return " ".join(parts).strip() or None


def create_openai_provider(
    *,
    api_key: str,
    model: str = DEFAULT_OPENAI_MODEL,
    timeout_seconds: float = DEFAULT_OPENAI_TIMEOUT_SECONDS,
    client: Any | None = None,
) -> ValidatingJSONConciergeProvider:
    backend = OpenAIIntentBackend(
        api_key=api_key,
        model=model,
        timeout_seconds=timeout_seconds,
        client=client,
    )
    return ValidatingJSONConciergeProvider(backend, name=f"openai:{backend.model}")


__all__ = [
    "DEFAULT_OPENAI_MODEL",
    "DEFAULT_OPENAI_TIMEOUT_SECONDS",
    "OpenAIIntentBackend",
    "OpenAIPlaybackIntent",
    "OpenAIRoutingPreference",
    "create_openai_provider",
]
