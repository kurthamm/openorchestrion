"""OpenAI adapter for the provider-neutral Music Concierge.

The import of the OpenAI SDK is deliberately lazy. Offline appliances neither
need nor install it, and merely importing :mod:`openorchestrion` must never make
a hosted-provider dependency mandatory.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from .ai import ProviderOutputError, ValidatingJSONConciergeProvider
from .models import PlaybackIntent

DEFAULT_OPENAI_MODEL = "gpt-5.6-luna"
DEFAULT_OPENAI_TIMEOUT_SECONDS = 15.0


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
        context = (
            "There is no current intent. Treat this as a replacement request."
            if current_intent is None
            else (
                "Current validated intent JSON follows. Return the complete merged intent, "
                "preserving unrelated preferences and hard include/exclude tags when this is "
                "a refinement:\n"
                + json.dumps(dict(current_intent), sort_keys=True)
            )
        )
        user_text = f"{context}\n\nUser music request:\n{prompt}"

        response = await self.client.responses.parse(
            model=self.model,
            instructions=contract,
            input=[{"role": "user", "content": user_text}],
            text_format=PlaybackIntent,
        )

        refusal = _refusal_text(response)
        if refusal:
            raise ProviderOutputError(f"OpenAI refused the request: {refusal}")

        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            raise ProviderOutputError("OpenAI returned no parsed PlaybackIntent")
        if not isinstance(parsed, PlaybackIntent):
            try:
                parsed = PlaybackIntent.model_validate(parsed)
            except Exception as exc:  # noqa: BLE001 - provider boundary
                raise ProviderOutputError("OpenAI parsed output was not a PlaybackIntent") from exc
        return parsed.model_dump(mode="json")


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
    "create_openai_provider",
]
