"""Server-side Concierge conversation state.

``docs/api-contract.md`` promises that successive refinements — "a little more
upbeat", "more piano" — build on the previous turn. That continuity lives here
rather than in the client, so a 7-inch kiosk does not have to resend the whole
intent on every turn and so every surface in the house sees the same
conversation when it uses the same ``session_id``.

The store is bounded and in-memory: conversation state is a convenience, not
durable data, and losing it on restart costs a user one extra sentence.
"""

from __future__ import annotations

from collections import OrderedDict

from ..ai import ConciergeSession, MusicConcierge

DEFAULT_MAX_SESSIONS = 64


class ConciergeSessions:
    """Bounded LRU of :class:`ConciergeSession` keyed by client-chosen id."""

    def __init__(
        self,
        concierge: MusicConcierge | None = None,
        *,
        max_sessions: int = DEFAULT_MAX_SESSIONS,
    ) -> None:
        if max_sessions < 1:
            raise ValueError("max_sessions must be at least 1")
        self.concierge = concierge or MusicConcierge()
        self.max_sessions = max_sessions
        self._sessions: OrderedDict[str, ConciergeSession] = OrderedDict()

    def get(self, session_id: str) -> ConciergeSession:
        session = self._sessions.get(session_id)
        if session is None:
            session = ConciergeSession(self.concierge)
            self._sessions[session_id] = session
            while len(self._sessions) > self.max_sessions:
                self._sessions.popitem(last=False)
        self._sessions.move_to_end(session_id)
        return session

    def reset(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        if session is not None:
            session.reset()

    def __len__(self) -> int:
        return len(self._sessions)

    def __contains__(self, session_id: object) -> bool:
        return session_id in self._sessions
