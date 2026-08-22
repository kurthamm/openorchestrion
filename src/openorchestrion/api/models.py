"""Response models for the OpenOrchestrion HTTP surface.

These models *are* the API contract described in ``docs/api-contract.md``.
FastAPI derives ``/openapi.json`` from them, so a generated client cannot drift
from what the backend actually returns. Changing a shape here is a contract
change and needs review from both the UI and playback sides.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..models import PlaybackIntent

# Stable, machine-readable error codes. The UI switches on these rather than
# parsing prose, so treat the strings as part of the contract.
#
# ``intent_invalid`` is reserved for failures inside a PlaybackIntent, so the UI
# can point the Concierge surface at the offending field. Any other malformed
# request — a bad query parameter, a malformed queue command — is
# ``request_invalid``.
ErrorCode = Literal[
    "intent_invalid",
    "request_invalid",
    "concierge_unavailable",
    "library_empty",
    "asset_not_found",
    "no_midi_output",
    "transport_conflict",
    "not_implemented",
    "internal_error",
]

TransportAction = Literal["play", "pause", "stop", "skip", "panic"]
TRANSPORT_ACTIONS: tuple[str, ...] = ("play", "pause", "stop", "skip", "panic")


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
    command_id: UUID | None = None
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
    command_id: UUID | None = None
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


class LibraryAssetDetail(LibraryAsset):
    """Single-asset view. Adds the deterministic facts a detail screen shows."""

    model_config = ConfigDict(extra="forbid")

    composition_id: str | None = None
    original_filename: str | None = None
    era: str | None = None
    year_composed: int | None = None
    track_count: int | None = None
    note_count: int | None = None
    sustain_used: bool | None = None
    percussion_note_count: int | None = None
    gm_assessment: str | None = None
    genres: list[str] = Field(default_factory=list)
    moods: list[str] = Field(default_factory=list)
    themes: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    instrumentation: list[str] = Field(default_factory=list)


class FavoriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    favorite: bool = True
    command_id: UUID | None = None


# --------------------------------------------------------------------------
# Playback, queue and transport (implemented by issue #14)
#
# These shapes are declared now so the UI can be written against their final
# form. The routes return ``not_implemented`` until the state machine exists,
# but the success models are what it must produce.
# --------------------------------------------------------------------------


class PositionAnchor(BaseModel):
    """A point-in-time reading of playback position.

    The client renders a smooth progress bar by interpolating from
    ``position_ms`` at ``rate``, **anchored at the moment the message was
    received locally** — never by subtracting ``server_time`` from its own
    clock. Browser and appliance clocks are independent and may differ by
    seconds; ``server_time`` exists for ordering and diagnostics only.

    ``rate`` is 0.0 while paused, so a paused client simply stops advancing.
    """

    model_config = ConfigDict(extra="forbid")

    position_ms: int = Field(ge=0)
    duration_ms: int | None = Field(default=None, ge=0)
    rate: float = Field(default=1.0, ge=0.0)
    server_time: str = Field(
        description="Server clock at emission. Ordering and diagnostics only; not a client anchor."
    )


class NowPlaying(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: str
    composition_id: str | None = None
    title: str
    composer: str | None = None
    duration_seconds: float
    queue_index: int | None = Field(default=None, ge=0)


class PlaybackState(BaseModel):
    """Authoritative transport state. The UI renders this; it never derives it."""

    model_config = ConfigDict(extra="forbid")

    state: Literal["idle", "playing", "paused", "stopped"]
    now_playing: NowPlaying | None = None
    position: PositionAnchor | None = None
    command_id: UUID | None = Field(
        default=None,
        description="Echoes the command that produced this state, so the "
        "originating client can clear its optimistic pending flag.",
    )


class QueueEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: str
    composition_id: str | None = None
    title: str
    composer: str | None = None
    duration_seconds: float
    index: int = Field(ge=0)


class QueueState(BaseModel):
    """The authoritative queue. Clients render it and send mutations."""

    model_config = ConfigDict(extra="forbid")

    items: list[QueueEntry] = Field(default_factory=list)
    current_index: int | None = Field(default=None, ge=0)
    total_duration_seconds: float = 0.0
    command_id: UUID | None = None


class TransportCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: UUID | None = Field(
        default=None,
        description="Client-generated. Commands are idempotent by this value, "
        "so a retry after a dropped connection does not double-skip a track.",
    )


class QueueReplaceRequest(BaseModel):
    """Fill the queue from exactly one source: an intent or explicit assets."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["replace", "append"] = "replace"
    intent: PlaybackIntent | None = None
    asset_ids: list[str] = Field(default_factory=list)
    seed: int = 0
    max_tracks: int = Field(default=25, ge=1, le=1000)
    command_id: UUID | None = None

    @model_validator(mode="after")
    def require_exactly_one_source(self) -> QueueReplaceRequest:
        has_intent = self.intent is not None
        has_assets = bool(self.asset_ids)
        if has_intent == has_assets:
            raise ValueError("provide exactly one of intent or non-empty asset_ids")
        return self


class QueueReorderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: str
    to_index: int = Field(ge=0)
    command_id: UUID | None = None


class QueueRemoveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: str
    command_id: UUID | None = None


# --------------------------------------------------------------------------
# WebSocket
# --------------------------------------------------------------------------


class SnapshotPayload(BaseModel):
    """Complete state, sent on connect and on resync.

    A client that sees a ``seq`` gap replaces its state from one of these
    wholesale rather than attempting to patch.
    """

    model_config = ConfigDict(extra="forbid")

    status: SystemStatus
    playback: PlaybackState
    queue: QueueState


class SocketEnvelopeBase(BaseModel):
    """``seq`` increases monotonically; a gap means resync, not patch."""

    model_config = ConfigDict(extra="forbid")

    seq: int = Field(ge=0)
    ts: str


class SnapshotEnvelope(SocketEnvelopeBase):
    type: Literal["state.snapshot"] = "state.snapshot"
    payload: SnapshotPayload


class PlaybackEnvelope(SocketEnvelopeBase):
    type: Literal["state.playback"] = "state.playback"
    payload: PlaybackState


class QueueEnvelope(SocketEnvelopeBase):
    type: Literal["state.queue"] = "state.queue"
    payload: QueueState


class DevicesEnvelope(SocketEnvelopeBase):
    type: Literal["state.devices"] = "state.devices"
    payload: OutputsState


class LibraryEnvelope(SocketEnvelopeBase):
    type: Literal["state.library"] = "state.library"
    payload: LibraryCounts


class ConciergeEnvelope(SocketEnvelopeBase):
    type: Literal["concierge.result"] = "concierge.result"
    payload: ConciergeResponse


class ErrorEnvelope(SocketEnvelopeBase):
    type: Literal["error"] = "error"
    payload: ErrorBody


SocketMessage = Annotated[
    SnapshotEnvelope
    | PlaybackEnvelope
    | QueueEnvelope
    | DevicesEnvelope
    | LibraryEnvelope
    | ConciergeEnvelope
    | ErrorEnvelope,
    Field(discriminator="type"),
]
