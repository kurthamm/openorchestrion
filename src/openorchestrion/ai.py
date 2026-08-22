from __future__ import annotations

import argparse
import asyncio
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping, Protocol

from pydantic import ValidationError

from .models import PerformanceType, PlaybackIntent

PROVIDER_CONTRACT = """You are the OpenOrchestrion Music Concierge intent interpreter.
Return one JSON object that validates as PlaybackIntent. Return the complete merged intent,
not a delta. You may describe listening preferences only. Never return filenames, catalog
claims, URLs, MIDI messages, SysEx, shell commands, device commands, or fields outside the
PlaybackIntent schema. The deterministic OpenOrchestrion selector decides what real music
exists and what is playable. If current_intent is supplied, conversational refinements such
as 'more upbeat' must preserve unrelated existing preferences.
"""


class ConciergeError(ValueError):
    pass


class ProviderOutputError(ConciergeError):
    pass


class MusicConciergeProvider(ABC):
    """Provider-neutral natural-language intent interface.

    Implementations interpret user language and return a fully validated PlaybackIntent.
    They do not receive catalog mutation APIs, playback engines, or MIDI ports.
    """

    name = "provider"

    @abstractmethod
    async def interpret(
        self,
        prompt: str,
        *,
        current_intent: PlaybackIntent | None = None,
    ) -> PlaybackIntent:
        raise NotImplementedError


class IntentBackend(Protocol):
    """Minimal adapter seam for a hosted/local structured-output model client."""

    async def generate_intent(
        self,
        *,
        prompt: str,
        current_intent: Mapping[str, Any] | None,
        contract: str,
    ) -> Mapping[str, Any] | str:
        ...


class CallableIntentBackend:
    """Wrap an async callable as an IntentBackend.

    This is useful for provider-specific adapters and deterministic fake providers in tests.
    """

    def __init__(
        self,
        callback: Callable[..., Awaitable[Mapping[str, Any] | str]],
    ) -> None:
        self._callback = callback

    async def generate_intent(
        self,
        *,
        prompt: str,
        current_intent: Mapping[str, Any] | None,
        contract: str,
    ) -> Mapping[str, Any] | str:
        return await self._callback(
            prompt=prompt,
            current_intent=current_intent,
            contract=contract,
        )


class ValidatingJSONConciergeProvider(MusicConciergeProvider):
    """Validate a model/backend JSON response at the AI/deterministic boundary."""

    def __init__(self, backend: IntentBackend, *, name: str = "structured-model") -> None:
        self.backend = backend
        self.name = name

    async def interpret(
        self,
        prompt: str,
        *,
        current_intent: PlaybackIntent | None = None,
    ) -> PlaybackIntent:
        if not prompt.strip():
            raise ConciergeError("prompt is required")
        raw = await self.backend.generate_intent(
            prompt=prompt,
            current_intent=(
                current_intent.model_dump(mode="json") if current_intent is not None else None
            ),
            contract=PROVIDER_CONTRACT,
        )
        if isinstance(raw, str):
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ProviderOutputError("provider did not return valid JSON") from exc
        elif isinstance(raw, Mapping):
            payload = dict(raw)
        else:
            raise ProviderOutputError(
                f"provider returned unsupported output type {type(raw).__name__}"
            )
        if not isinstance(payload, dict):
            raise ProviderOutputError("provider output must be one JSON object")
        try:
            return PlaybackIntent.model_validate(payload)
        except ValidationError as exc:
            raise ProviderOutputError(f"provider output failed PlaybackIntent validation: {exc}") from exc


class DisabledConciergeProvider(MusicConciergeProvider):
    name = "disabled"

    async def interpret(
        self,
        prompt: str,
        *,
        current_intent: PlaybackIntent | None = None,
    ) -> PlaybackIntent:
        raise RuntimeError("AI Music Concierge is disabled")


_WORD_NUMBERS = {
    "a": 1.0,
    "an": 1.0,
    "one": 1.0,
    "two": 2.0,
    "three": 3.0,
    "four": 4.0,
    "five": 5.0,
    "six": 6.0,
    "eight": 8.0,
    "ten": 10.0,
}
_LEVEL_ORDER = ("low", "medium", "high")


def _duration_minutes(text: str) -> int | None:
    lowered = text.casefold()
    token = r"(\d+(?:\.\d+)?|a|an|one|two|three|four|five|six|eight|ten)"
    hours = re.search(rf"\b{token}\s*hours?\b", lowered)
    if hours:
        raw = hours.group(1)
        value = _WORD_NUMBERS.get(raw, float(raw) if raw.replace(".", "", 1).isdigit() else 1.0)
        return max(1, round(value * 60))
    minutes = re.search(rf"\b{token}\s*minutes?\b", lowered)
    if minutes:
        raw = minutes.group(1)
        value = _WORD_NUMBERS.get(raw, float(raw) if raw.replace(".", "", 1).isdigit() else 1.0)
        return max(1, round(value))
    return None


def _append_unique(values: list[str], value: str) -> None:
    if value.casefold() not in {item.casefold() for item in values}:
        values.append(value)


def _remove_casefold(values: list[str], value: str) -> None:
    target = value.casefold()
    values[:] = [item for item in values if item.casefold() != target]


def _step_level(current: str | None, direction: int, *, default: str) -> str:
    if current not in _LEVEL_ORDER:
        return default
    index = _LEVEL_ORDER.index(current)
    return _LEVEL_ORDER[max(0, min(len(_LEVEL_ORDER) - 1, index + direction))]


def _looks_like_refinement(text: str, current: PlaybackIntent | None) -> bool:
    if current is None:
        return False
    lowered = text.strip().casefold()
    markers = (
        "more ",
        "less ",
        "a little ",
        "make it ",
        "add ",
        "also ",
        "but ",
        "instead ",
        "not so ",
        "quieter",
        "louder",
    )
    return lowered.startswith(markers) or len(lowered.split()) <= 4


def _interpretation(intent: PlaybackIntent) -> str:
    parts: list[str] = []
    if intent.energy:
        parts.append(f"{intent.energy}-energy")
    if intent.familiarity:
        parts.append(f"{intent.familiarity}-familiarity")
    if intent.themes:
        parts.append("/".join(intent.themes))
    if intent.genres:
        parts.append("/".join(intent.genres))
    if intent.moods:
        parts.append("/".join(intent.moods))
    if intent.instrumentation:
        parts.append("/".join(intent.instrumentation))
    if intent.performance_types:
        parts.append("/".join(value.value.replace("_", " ").lower() for value in intent.performance_types))
    description = ", ".join(parts) if parts else "general music"
    if intent.duration_minutes:
        description += f" for about {intent.duration_minutes} minutes"
    return description[:500]


class DeterministicConciergeProvider(MusicConciergeProvider):
    """Offline, deterministic fallback for common household music requests.

    This is intentionally modest. It preserves useful control when a model is unavailable and
    provides a reproducible test oracle. It does not pretend to replace a general language model.
    """

    name = "deterministic-fallback"

    async def interpret(
        self,
        prompt: str,
        *,
        current_intent: PlaybackIntent | None = None,
    ) -> PlaybackIntent:
        text = prompt.strip()
        if not text:
            raise ConciergeError("prompt is required")
        lowered = text.casefold()
        refining = _looks_like_refinement(text, current_intent)
        intent = (
            current_intent.model_copy(deep=True)
            if refining and current_intent is not None
            else PlaybackIntent()
        )
        intent.mode = "station"
        intent.continuation_behavior = "refine" if refining else "replace"

        duration = _duration_minutes(text)
        if duration is not None:
            intent.duration_minutes = duration

        # Themes / occasions
        if "dinner" in lowered or "while we eat" in lowered:
            _append_unique(intent.themes, "dinner")
        if any(word in lowered for word in ("christmas", "xmas")):
            _append_unique(intent.themes, "Christmas")
        if "holiday" in lowered:
            _append_unique(intent.themes, "holiday")
        if any(word in lowered for word in ("cocktail", "cocktails")):
            _append_unique(intent.themes, "cocktail")

        # Genres
        for token, label in (
            ("classical", "classical"),
            ("ragtime", "ragtime"),
            ("jazz", "jazz"),
            ("broadway", "Broadway"),
            ("pop ", "pop"),
        ):
            if token in lowered:
                _append_unique(intent.genres, label)

        # Mood / energy
        if any(word in lowered for word in ("relaxing", "relaxed", "calm", "quiet")):
            _append_unique(intent.moods, "relaxed")
            if not refining or intent.energy is None:
                intent.energy = "low"
        if "elegant" in lowered:
            _append_unique(intent.moods, "elegant")
        if "reflective" in lowered:
            _append_unique(intent.moods, "reflective")
        if "nothing too dramatic" in lowered or "not too dramatic" in lowered:
            intent.energy = "low"
            _append_unique(intent.exclude_tags, "dramatic")
        if "more upbeat" in lowered or "a little more upbeat" in lowered:
            intent.energy = _step_level(intent.energy, 1, default="medium")
        elif "upbeat" in lowered:
            intent.energy = "high"
        if any(phrase in lowered for phrase in ("less upbeat", "quieter", "calmer")):
            intent.energy = _step_level(intent.energy, -1, default="low")

        # Familiarity
        if "more recognizable" in lowered or "more familiar" in lowered:
            intent.familiarity = _step_level(intent.familiarity, 1, default="high")
        elif any(word in lowered for word in ("popular", "recognizable", "familiar")):
            intent.familiarity = "high"

        # Composer preferences
        if "joplin" in lowered:
            _append_unique(intent.composers, "Scott Joplin")

        # Instrumentation and performance type
        if "dueling piano" in lowered or "dueling pianos" in lowered:
            _append_unique(intent.instrumentation, "piano")
            intent.performance_types = [PerformanceType.DUELING_PIANO]
        elif "two piano" in lowered or "two pianos" in lowered:
            _append_unique(intent.instrumentation, "piano")
            intent.performance_types = [PerformanceType.TWO_PIANO]
        if "solo piano" in lowered:
            _append_unique(intent.instrumentation, "piano")
            intent.performance_types = [PerformanceType.SOLO_PIANO]
        if "piano" in lowered:
            _append_unique(intent.instrumentation, "piano")
        if "more piano" in lowered:
            _append_unique(intent.instrumentation, "piano")
        if "orchestral" in lowered or "orchestra" in lowered:
            _append_unique(intent.instrumentation, "orchestra")
            if "instead of solo piano" in lowered:
                _remove_casefold(intent.instrumentation, "piano")
                intent.performance_types = [PerformanceType.MULTI_INSTRUMENT]
        if "small ensemble" in lowered:
            _append_unique(intent.instrumentation, "small ensemble")

        intent.interpretation = _interpretation(intent)
        return PlaybackIntent.model_validate(intent.model_dump(mode="json"))


@dataclass(frozen=True, slots=True)
class ConciergeResult:
    intent: PlaybackIntent
    provider: str
    fallback_used: bool
    primary_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent.model_dump(mode="json"),
            "provider": self.provider,
            "fallback_used": self.fallback_used,
            "primary_error": self.primary_error,
        }


class MusicConcierge:
    """Resilient application service around a primary provider and offline fallback."""

    def __init__(
        self,
        primary: MusicConciergeProvider | None = None,
        *,
        fallback: MusicConciergeProvider | None = None,
    ) -> None:
        self.primary = primary
        self.fallback = fallback or DeterministicConciergeProvider()

    async def interpret(
        self,
        prompt: str,
        *,
        current_intent: PlaybackIntent | None = None,
    ) -> ConciergeResult:
        primary_error: str | None = None
        if self.primary is not None:
            try:
                intent = await self.primary.interpret(prompt, current_intent=current_intent)
                return ConciergeResult(intent, self.primary.name, False, None)
            except Exception as exc:  # provider failures must not disable local control
                primary_error = f"{type(exc).__name__}: {exc}"
        intent = await self.fallback.interpret(prompt, current_intent=current_intent)
        return ConciergeResult(intent, self.fallback.name, self.primary is not None, primary_error)


class ConciergeSession:
    """Conversation state for successive natural-language refinements."""

    def __init__(self, concierge: MusicConcierge | None = None) -> None:
        self.concierge = concierge or MusicConcierge()
        self.current_intent: PlaybackIntent | None = None
        self.turns: list[ConciergeResult] = []

    async def ask(self, prompt: str) -> ConciergeResult:
        result = await self.concierge.interpret(prompt, current_intent=self.current_intent)
        self.current_intent = result.intent.model_copy(deep=True)
        self.turns.append(result)
        return result

    def reset(self) -> None:
        self.current_intent = None
        self.turns.clear()


def _load_intent(path: str | None) -> PlaybackIntent | None:
    if path is None:
        return None
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return PlaybackIntent.model_validate(payload)


async def _cli_run(args: argparse.Namespace) -> ConciergeResult:
    provider = DeterministicConciergeProvider()
    return await MusicConcierge(primary=None, fallback=provider).interpret(
        args.prompt,
        current_intent=_load_intent(args.current_intent_json),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Interpret a music request as a validated PlaybackIntent using the "
            "deterministic offline Concierge fallback."
        )
    )
    parser.add_argument("prompt", help="Natural-language music request")
    parser.add_argument("--current-intent-json", help="Existing intent for a refinement turn")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = asyncio.run(_cli_run(args))
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    else:
        print(result.intent.interpretation or "Music request interpreted")
        print(json.dumps(result.intent.model_dump(mode="json"), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
