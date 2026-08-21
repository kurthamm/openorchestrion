from __future__ import annotations

from abc import ABC, abstractmethod

from .models import PlaybackIntent


class MusicConciergeProvider(ABC):
    """Provider-neutral natural-language intent interface.

    Implementations interpret user language and return a PlaybackIntent.
    They do not receive or control MIDI ports.
    """

    @abstractmethod
    async def interpret(
        self,
        prompt: str,
        *,
        current_intent: PlaybackIntent | None = None,
    ) -> PlaybackIntent:
        raise NotImplementedError


class DisabledConciergeProvider(MusicConciergeProvider):
    async def interpret(
        self,
        prompt: str,
        *,
        current_intent: PlaybackIntent | None = None,
    ) -> PlaybackIntent:
        raise RuntimeError("AI Music Concierge is disabled")
