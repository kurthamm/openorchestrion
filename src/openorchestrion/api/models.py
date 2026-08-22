"""Response models for the OpenOrchestrion HTTP surface.

These models *are* the API contract described in ``docs/api-contract.md``.
FastAPI derives ``/openapi.json`` from them, so a generated client cannot drift
from what the backend actually returns. Changing a shape here is a contract
change and needs review from both the UI and playback sides.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..models import PlaybackIntent

# Stable, machine-readable error codes. The UI switches on these rather than
# parsing prose, so treat the strings as part of the contract.
ErrorCode = Literal[
    "intent_invalid",
    "concierge_unavailable",
    "library_empty",
    "asset_not_found",
    "no_midi_output",
    "transport_conflict",
    "not_implemented",
]


class ErrorBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: ErrorCode
    message: str
    detail: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    """The only error shape the API returns. Never a bare 500 with HTML."""

    model_config = ConfigDict(extra="forbid")

    error: ErrorBody


class AiState(BaseModel):
    """Whether natural-language control is available, and why not when it isn't.

    Absence of a provider is a normal, renderable state — not an error.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool
    provider: str | None = None
    reason: str | None = None


class OutputsState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ready: bool
    devices: list[str] = Field(default_factory=list)
    reason: str | None = None


class LibraryCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    indexed: bool
    assets: int = 0
    compositions: int = 0
    genres: int = 0
    moods: int = 0
    themes: int = 0


class SystemStatus(BaseModel):
    """Aggregate appliance state for the Now Playing header and status screens."""

    model_config = ConfigDict(extra="forbid")

    phase: Literal["bootstrap", "ready", "playing", "degraded"]
    playing: bool
    ai: AiState
    outputs: OutputsState
    library: LibraryCounts


class LibraryAsset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: str
    title: str | None = None
    composer: str | None = None
    artist: str | None = None
    performance_type: str | None = None
    quality_grade: str | None = None
    familiarity: int | None = None
    energy: int | None = None
    favorite: bool = False
    duration_seconds: float = 0.0
    rights_status: str | None = None
    peak_simultaneous_notes: int | None = None


class LibrarySearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[LibraryAsset] = Field(default_factory=list)
    count: int = 0


class QueueItemModel(BaseModel):
    """Mirrors ``stations.QueueItem`` so the UI can explain each selection."""

    model_config = ConfigDict(extra="forbid")

    asset_id: str
    composition_id: str | None = None
    title: str
    composer: str | None = None
    duration_seconds: float
    midi_path: str
    score: float
    base_score: float
    match_tier: int
    selected_for: list[str] = Field(default_factory=list)
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    sequence_adjustments: dict[str, float] = Field(default_factory=dict)


class StationQueueModel(BaseModel):
    """Mirrors ``stations.StationQueue``.

    ``relaxations`` is meant to be rendered, not swallowed: when the selector
    could not honour the request it says so, and the appliance should pass that
    on rather than silently serving something else.
    """

    model_config = ConfigDict(extra="forbid")

    seed: int
    requested_duration_seconds: int | None = None
    total_duration_seconds: float
    candidate_assets: int
    candidate_compositions: int
    items: list[QueueItemModel] = Field(default_factory=list)
    relaxations: list[str] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)


class StationPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: PlaybackIntent
    seed: int = 0
    max_tracks: int = Field(default=25, ge=1, le=1000)


class ConciergeAskRequest(BaseModel):
    """Envelope for a natural-language request.

    Correlation lives here rather than inside ``PlaybackIntent``, which forbids
    extra fields so that model output cannot smuggle in new instructions.
    """

    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1, max_length=2000)
    command_id: str | None = None
    session_id: str | None = None
    current_intent: PlaybackIntent | None = None


class ConciergeResponse(BaseModel):
    """Mirrors ``ai.ConciergeResult`` plus the queue the UI needs to render.

    When ``fallback_used`` is true the request was answered by the offline
    deterministic interpreter; the UI should say so rather than presenting a
    degraded answer as a normal one.
    """

    model_config = ConfigDict(extra="forbid")

    intent: PlaybackIntent
    provider: str
    fallback_used: bool
    primary_error: str | None = None
    command_id: str | None = None
    preview: StationQueueModel | None = None


class HistoryEntry(BaseModel):
    """Mirrors ``history.HistorySummary``."""

    model_config = ConfigDict(extra="forbid")

    asset_id: str
    composition_id: str | None = None
    qualifying_play_count: int
    last_played_at: str | None = None
    total_played_seconds: float
    completed_count: int
    skipped_after_substantial_count: int


class HistoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[HistoryEntry] = Field(default_factory=list)
    count: int = 0


class DevicesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outputs: OutputsState


class SocketEnvelope(BaseModel):
    """Envelope for every WebSocket message in both directions.

    ``seq`` increases monotonically; a gap tells the client to request a fresh
    snapshot rather than attempt to patch its local state.
    """

    model_config = ConfigDict(extra="forbid")

    type: str
    seq: int
    ts: str
    payload: dict[str, Any] = Field(default_factory=dict)
