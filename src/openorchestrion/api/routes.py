"""HTTP routes implementing ``docs/api-contract.md``.

Endpoints backed by an existing domain module call it directly — the API adds no
selection, scoring or timing logic of its own. Endpoints owned by the playback
state machine (issue #14) are declared here and return ``not_implemented`` so
they appear in the generated OpenAPI schema and the UI can wire against their
final shape before the backend exists.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request, WebSocket

from ..ai import ConciergeResult, MusicConcierge
from ..library.catalog import catalog_stats, get_asset, search_catalog
from ..midi.devices import list_output_ports
from ..models import PlaybackIntent
from ..stations import build_station
from .errors import ApiError
from .models import (
    TRANSPORT_ACTIONS,
    AiState,
    ConciergeAskRequest,
    ConciergeResponse,
    DevicesResponse,
    ErrorBody,
    ErrorEnvelope,
    ErrorResponse,
    FavoriteRequest,
    HistoryEntry,
    HistoryResponse,
    LibraryAsset,
    LibraryAssetDetail,
    LibraryCounts,
    LibrarySearchResponse,
    OutputsState,
    PlaybackState,
    QueueRemoveRequest,
    QueueReorderRequest,
    QueueReplaceRequest,
    QueueState,
    StationPreviewRequest,
    StationQueueModel,
    SystemStatus,
    TransportCommand,
)
from .sessions import ConciergeSessions
from .settings import Settings

router = APIRouter(prefix="/api")

# Declared alongside the real success model on #14-owned routes: the generated
# client learns both the eventual success shape and the interim failure shape.
_PENDING_PLAYBACK: dict[int | str, dict[str, Any]] = {
    501: {
        "model": ErrorResponse,
        "description": "Not yet implemented: awaiting the playback state machine (#14)",
    }
}
_PENDING_METADATA_WRITER: dict[int | str, dict[str, Any]] = {
    501: {
        "model": ErrorResponse,
        "description": (
            "Not yet implemented: awaiting a descriptive_metadata writer. "
            "Independent of #14."
        ),
    }
}


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _concierge(request: Request) -> MusicConcierge:
    return request.app.state.concierge


def _sessions(request: Request) -> ConciergeSessions:
    return request.app.state.concierge_sessions


def _pending(feature: str) -> ApiError:
    return ApiError(
        "not_implemented",
        f"{feature} arrives with the playback state machine (issue #14)",
        status_code=501,
    )


def _outputs_state() -> OutputsState:
    """Report MIDI availability without letting a missing backend fail the request.

    A developer machine with no ALSA backend is a normal degraded state, not an
    error: the UI still renders, it just cannot offer playback.
    """
    try:
        devices = list_output_ports()
    except Exception as exc:  # noqa: BLE001 - any backend failure is a renderable state
        return OutputsState(ready=False, devices=[], reason=f"{type(exc).__name__}: {exc}")
    if not devices:
        return OutputsState(ready=False, devices=[], reason="no_midi_output")
    return OutputsState(ready=True, devices=devices)


def _library_counts(catalog_db: Path) -> LibraryCounts:
    if not catalog_db.is_file():
        return LibraryCounts(indexed=False)
    stats = catalog_stats(catalog_db)
    return LibraryCounts(indexed=True, **stats)


def _require_catalog(settings: Settings) -> Path:
    if not settings.catalog_db.is_file():
        raise ApiError(
            "library_empty",
            "No catalog has been built yet. Import MIDI files and run openorchestrion-reindex.",
            status_code=409,
            detail={"expected_path": str(settings.catalog_db)},
        )
    return settings.catalog_db


def _queue_model(queue: Any) -> StationQueueModel:
    return StationQueueModel.model_validate(queue.to_dict())


@router.get("/health", response_model=dict[str, str])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/status", response_model=SystemStatus)
async def status(request: Request) -> SystemStatus:
    settings = _settings(request)
    concierge = _concierge(request)
    outputs = _outputs_state()
    library = _library_counts(settings.catalog_db)
    ai = AiState(
        enabled=True,
        provider=concierge.primary.name if concierge.primary else concierge.fallback.name,
        reason=None if concierge.primary else "no_provider_configured_using_offline_interpreter",
    )
    if not library.indexed or not outputs.ready:
        phase: str = "degraded"
    else:
        phase = "ready"
    return SystemStatus(
        phase=phase,  # type: ignore[arg-type]
        playing=False,
        ai=ai,
        outputs=outputs,
        library=library,
    )


@router.get("/devices", response_model=DevicesResponse)
async def devices() -> DevicesResponse:
    return DevicesResponse(outputs=_outputs_state())


async def _interpret(request: Request, payload: ConciergeAskRequest) -> ConciergeResult:
    """Run one Concierge turn, continuing a server-side conversation if asked.

    With a ``session_id`` the turn builds on that session's previous intent, so
    "a little more upbeat" refines rather than starts over. An explicit
    ``current_intent`` overrides the remembered one, which lets a client resync
    the conversation after its own state was lost. Without a ``session_id`` the
    call is stateless.
    """
    if payload.session_id is None:
        return await _concierge(request).interpret(
            payload.prompt,
            current_intent=payload.current_intent,
        )
    session = _sessions(request).get(payload.session_id)
    if payload.current_intent is not None:
        session.current_intent = payload.current_intent.model_copy(deep=True)
    return await session.ask(payload.prompt)


@router.post("/concierge/ask", response_model=ConciergeResponse)
async def concierge_ask(request: Request, payload: ConciergeAskRequest) -> ConciergeResponse:
    """Interpret natural language into a validated intent, with a queue preview.

    The offline deterministic interpreter answers when no provider is
    configured, so this endpoint works with no network and no API key.
    """
    settings = _settings(request)
    result = await _interpret(request, payload)
    preview: StationQueueModel | None = None
    if settings.catalog_db.is_file():
        preview = _queue_model(build_station(settings.catalog_db, result.intent))
    return ConciergeResponse(
        intent=result.intent,
        provider=result.provider,
        fallback_used=result.fallback_used,
        primary_error=result.primary_error,
        command_id=payload.command_id,
        preview=preview,
    )


@router.post("/stations/preview", response_model=StationQueueModel)
async def stations_preview(request: Request, payload: StationPreviewRequest) -> StationQueueModel:
    catalog_db = _require_catalog(_settings(request))
    queue = build_station(
        catalog_db,
        payload.intent,
        seed=payload.seed,
        max_tracks=payload.max_tracks,
    )
    return _queue_model(queue)


@router.post("/intent/validate", response_model=PlaybackIntent)
async def validate_intent(intent: PlaybackIntent) -> PlaybackIntent:
    """Echo a validated intent. Retained so existing clients keep working."""
    return intent


@router.get("/library/stats", response_model=LibraryCounts)
async def library_stats(request: Request) -> LibraryCounts:
    return _library_counts(_settings(request).catalog_db)


@router.get("/library/search", response_model=LibrarySearchResponse)
async def library_search(
    request: Request,
    text: str | None = None,
    composer: str | None = None,
    genre: Annotated[list[str], Query()] = [],  # noqa: B006 - FastAPI query list
    mood: Annotated[list[str], Query()] = [],  # noqa: B006 - FastAPI query list
    theme: Annotated[list[str], Query()] = [],  # noqa: B006 - FastAPI query list
    performance_type: str | None = None,
    rights_status: str | None = None,
    min_familiarity: int | None = None,
    max_energy: int | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 50,
) -> LibrarySearchResponse:
    settings = _settings(request)
    if not settings.catalog_db.is_file():
        return LibrarySearchResponse(items=[], count=0)
    rows = search_catalog(
        settings.catalog_db,
        text=text,
        composer=composer,
        genres=genre,
        moods=mood,
        themes=theme,
        performance_type=performance_type,
        rights_status=rights_status,
        min_familiarity=min_familiarity,
        max_energy=max_energy,
        limit=limit,
    )
    items = [
        LibraryAsset(
            asset_id=row["asset_id"],
            title=row["title"],
            composer=row["composer"],
            artist=row["artist"],
            performance_type=row["performance_type"],
            quality_grade=row["quality_grade"],
            familiarity=row["familiarity"],
            energy=row["energy"],
            favorite=bool(row["favorite"]),
            duration_seconds=row["duration_seconds"],
            rights_status=row["rights_status"],
            peak_simultaneous_notes=row["peak_simultaneous_notes"],
        )
        for row in rows
    ]
    return LibrarySearchResponse(items=items, count=len(items))


@router.get("/history/recent", response_model=HistoryResponse)
async def history_recent(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=1000)] = 50,
) -> HistoryResponse:
    """Most recently played first.

    ``history_summaries`` orders oldest-first because staleness ranking wants it
    that way; the UI wants the opposite, so reverse here rather than asking the
    frontend to know that.
    """
    settings = _settings(request)
    if not settings.history_db.is_file():
        return HistoryResponse(items=[], count=0)
    from ..history import history_summaries

    summaries = list(reversed(history_summaries(settings.history_db)))[:limit]
    items = [HistoryEntry.model_validate(summary.to_dict()) for summary in summaries]
    return HistoryResponse(items=items, count=len(items))


@router.get(
    "/library/assets/{asset_id}",
    response_model=LibraryAssetDetail,
    responses={404: {"model": ErrorResponse, "description": "No such asset in the catalog"}},
)
async def library_asset(request: Request, asset_id: str) -> LibraryAssetDetail:
    settings = _settings(request)
    record = None
    if settings.catalog_db.is_file():
        record = get_asset(settings.catalog_db, asset_id)
    if record is None:
        raise ApiError(
            "asset_not_found",
            f"no indexed asset {asset_id}",
            status_code=404,
            detail={"asset_id": asset_id},
        )
    record.pop("midi_path", None)
    record.pop("metadata_path", None)
    return LibraryAssetDetail.model_validate(record)


@router.post(
    "/library/assets/{asset_id}/favorite",
    response_model=LibraryAssetDetail,
    responses=_PENDING_METADATA_WRITER,
)
async def set_favorite(asset_id: str, payload: FavoriteRequest) -> LibraryAssetDetail:
    """Blocked on the metadata writer, not on #14.

    ``favorite`` lives in the sidecar's ``descriptive_metadata`` block and
    nothing in the project writes to that block yet, so this cannot persist.
    Success returns the updated asset.
    """
    raise ApiError(
        "not_implemented",
        "Favorites need a descriptive_metadata writer before they can persist.",
        status_code=501,
        detail={"asset_id": asset_id, "requested": payload.favorite},
    )


@router.get("/queue", response_model=QueueState, responses=_PENDING_PLAYBACK)
async def get_queue() -> QueueState:
    raise _pending("Queue state")


@router.post("/queue", response_model=QueueState, responses=_PENDING_PLAYBACK)
async def replace_queue(payload: QueueReplaceRequest) -> QueueState:
    """Fill the queue from an intent or explicit assets, replacing or appending."""
    raise _pending("Queue mutation")


@router.post("/queue/reorder", response_model=QueueState, responses=_PENDING_PLAYBACK)
async def reorder_queue(payload: QueueReorderRequest) -> QueueState:
    raise _pending("Queue reordering")


@router.post("/queue/remove", response_model=QueueState, responses=_PENDING_PLAYBACK)
async def remove_from_queue(payload: QueueRemoveRequest) -> QueueState:
    raise _pending("Queue removal")


@router.post("/transport/{action}", response_model=PlaybackState, responses=_PENDING_PLAYBACK)
async def transport(action: str, payload: TransportCommand | None = None) -> PlaybackState:
    """Apply a transport action and return the resulting authoritative state."""
    if action not in TRANSPORT_ACTIONS:
        raise ApiError(
            "transport_conflict",
            f"unknown transport action: {action}",
            status_code=422,
            detail={"allowed": list(TRANSPORT_ACTIONS)},
        )
    raise _pending(f"Transport '{action}'")


@router.websocket("/ws")
async def state_socket(websocket: WebSocket) -> None:
    """Accept, report that state streaming is pending, and close.

    Connecting succeeds so the UI can exercise its reconnect path now, against
    the same typed envelope snapshots and deltas will use.
    """
    await websocket.accept()
    envelope = ErrorEnvelope(
        seq=0,
        ts=datetime.now(UTC).isoformat(),
        payload=ErrorBody(
            code="not_implemented",
            message="State streaming arrives with the playback state machine (issue #14)",
        ),
    )
    await websocket.send_json(envelope.model_dump())
    await websocket.close(code=1011)
