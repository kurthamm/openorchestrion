"""HTTP and WebSocket surface for the OpenOrchestrion application."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request, WebSocket, WebSocketDisconnect

from ..ai import ConciergeResult, MusicConcierge
from ..history import apply_no_repeat_window
from ..library.catalog import catalog_stats, get_asset, reindex_asset, search_catalog
from ..library.metadata import (
    AssetNotFoundError,
    MetadataConflictError,
    MetadataError,
    set_favorite,
)
from ..models import PlaybackIntent
from ..playback import (
    PlaybackConflict,
    PlaybackEngine,
    PlaybackError,
    PlaybackOutputError,
    QueueItemSpec,
)
from ..stations import StationConstraints, build_station
from .errors import ApiError
from .models import (
    TRANSPORT_ACTIONS,
    AiState,
    ConciergeAskRequest,
    ConciergeEnvelope,
    ConciergeResponse,
    DevicesEnvelope,
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
    LibraryEnvelope,
    LibrarySearchResponse,
    OutputsState,
    PlaybackEnvelope,
    PlaybackState,
    QueueEnvelope,
    QueueRemoveRequest,
    QueueReorderRequest,
    QueueReplaceRequest,
    QueueState,
    SnapshotEnvelope,
    SnapshotPayload,
    StationPreviewRequest,
    StationQueueModel,
    SystemStatus,
    TransportCommand,
)
from .sessions import ConciergeSessions
from .settings import Settings

router = APIRouter(prefix="/api")
Connection = Request | WebSocket

def _settings(connection: Connection) -> Settings:
    return connection.app.state.settings


def _concierge(connection: Connection) -> MusicConcierge:
    return connection.app.state.concierge


def _sessions(request: Request) -> ConciergeSessions:
    return request.app.state.concierge_sessions


def _playback(connection: Connection) -> PlaybackEngine:
    return connection.app.state.playback


def _outputs_state(connection: Connection) -> OutputsState:
    playback = _playback(connection)
    devices = list(playback.output_names)
    if not playback.outputs_ready:
        return OutputsState(ready=False, devices=[], reason="no_midi_output")
    return OutputsState(ready=True, devices=devices, reason=None)


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


def _station_queue_model(queue: Any) -> StationQueueModel:
    return StationQueueModel.model_validate(queue.to_dict())


def _queue_state_model(snapshot: Any) -> QueueState:
    return QueueState.model_validate(snapshot.to_dict())


def _playback_state_model(snapshot: Any) -> PlaybackState:
    return PlaybackState.model_validate(snapshot.to_dict())


async def _system_status(connection: Connection) -> SystemStatus:
    settings = _settings(connection)
    concierge = _concierge(connection)
    outputs = _outputs_state(connection)
    library = _library_counts(settings.catalog_db)
    playback = await _playback(connection).playback_snapshot()
    ai = AiState(
        enabled=True,
        provider=concierge.primary.name if concierge.primary else concierge.fallback.name,
        reason=None if concierge.primary else "no_provider_configured_using_offline_interpreter",
    )
    if playback.state == "playing":
        phase = "playing"
    elif not library.indexed or not outputs.ready:
        phase = "degraded"
    else:
        phase = "ready"
    return SystemStatus(
        phase=phase,
        playing=playback.state == "playing",
        ai=ai,
        outputs=outputs,
        library=library,
    )


def _translate_playback_error(exc: Exception) -> ApiError:
    if isinstance(exc, PlaybackConflict):
        return ApiError("transport_conflict", str(exc), status_code=409)
    if isinstance(exc, PlaybackOutputError):
        return ApiError("no_midi_output", str(exc), status_code=409)
    if isinstance(exc, PlaybackError):
        return ApiError(
            "internal_error",
            "Playback failed. Check the server log.",
            status_code=500,
        )
    raise exc


def _asset_spec(record: dict[str, Any], settings: Settings) -> QueueItemSpec:
    relative_path = Path(str(record["midi_path"]))
    midi_path = relative_path if relative_path.is_absolute() else settings.library_root / relative_path
    title = record.get("title") or record.get("original_filename") or record["asset_id"]
    return QueueItemSpec(
        asset_id=record["asset_id"],
        composition_id=record.get("composition_id"),
        title=title,
        composer=record.get("composer"),
        duration_seconds=float(record["duration_seconds"]),
        midi_path=str(midi_path),
    )


def _station_constraints(settings: Settings, intent: PlaybackIntent) -> StationConstraints:
    constraints = StationConstraints()
    if (
        intent.avoid_recent_repeats
        and intent.repeat_window_days is not None
        and settings.history_db.is_file()
    ):
        constraints = apply_no_repeat_window(
            constraints,
            settings.history_db,
            days=intent.repeat_window_days,
        )
    return constraints


def _queue_specs(payload: QueueReplaceRequest, settings: Settings) -> list[QueueItemSpec]:
    catalog_db = _require_catalog(settings)
    if payload.intent is not None:
        station = build_station(
            catalog_db,
            payload.intent,
            constraints=_station_constraints(settings, payload.intent),
            seed=payload.seed,
            max_tracks=payload.max_tracks,
        )
        if not station.items:
            raise ApiError(
                "library_empty",
                "No playable catalog items matched this request.",
                status_code=409,
            )
        specs: list[QueueItemSpec] = []
        for item in station.items:
            path = Path(item.midi_path)
            midi_path = path if path.is_absolute() else settings.library_root / path
            specs.append(
                QueueItemSpec(
                    asset_id=item.asset_id,
                    composition_id=item.composition_id,
                    title=item.title,
                    composer=item.composer,
                    duration_seconds=item.duration_seconds,
                    midi_path=str(midi_path),
                )
            )
        return specs

    specs = []
    for asset_id in payload.asset_ids:
        record = get_asset(catalog_db, asset_id)
        if record is None:
            raise ApiError(
                "asset_not_found",
                f"no indexed asset {asset_id}",
                status_code=404,
                detail={"asset_id": asset_id},
            )
        specs.append(_asset_spec(record, settings))
    return specs


@router.get("/health", response_model=dict[str, str])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/status", response_model=SystemStatus)
async def status(request: Request) -> SystemStatus:
    return await _system_status(request)


@router.get("/devices", response_model=DevicesResponse)
async def devices(request: Request) -> DevicesResponse:
    return DevicesResponse(outputs=_outputs_state(request))


async def _interpret(request: Request, payload: ConciergeAskRequest) -> ConciergeResult:
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
    settings = _settings(request)
    result = await _interpret(request, payload)
    preview: StationQueueModel | None = None
    if settings.catalog_db.is_file():
        preview = _station_queue_model(
            build_station(
                settings.catalog_db,
                result.intent,
                constraints=_station_constraints(settings, result.intent),
            )
        )
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
    settings = _settings(request)
    catalog_db = _require_catalog(settings)
    queue = build_station(
        catalog_db,
        payload.intent,
        constraints=_station_constraints(settings, payload.intent),
        seed=payload.seed,
        max_tracks=payload.max_tracks,
    )
    return _station_queue_model(queue)


@router.post("/intent/validate", response_model=PlaybackIntent)
async def validate_intent(intent: PlaybackIntent) -> PlaybackIntent:
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
    record = get_asset(settings.catalog_db, asset_id) if settings.catalog_db.is_file() else None
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
    responses={
        404: {"model": ErrorResponse, "description": "No such asset in the catalog"},
        409: {"model": ErrorResponse, "description": "The asset changed since it was read"},
    },
)
async def set_favorite_endpoint(
    request: Request,
    asset_id: str,
    payload: FavoriteRequest,
) -> LibraryAssetDetail:
    """Persist a favorite on the durable sidecar, then reconcile the index.

    The sidecar is the source of truth, so it is written first; the catalog is
    refreshed afterwards and would be rebuilt from the sidecar anyway.
    """
    settings = _settings(request)
    try:
        set_favorite(settings.library_root, asset_id, payload.favorite)
    except AssetNotFoundError as exc:
        raise ApiError(
            "asset_not_found",
            str(exc),
            status_code=404,
            detail={"asset_id": asset_id},
        ) from exc
    except MetadataConflictError as exc:
        raise ApiError(
            "request_invalid",
            str(exc),
            status_code=409,
            detail={"asset_id": asset_id},
        ) from exc
    except MetadataError as exc:
        raise ApiError(
            "request_invalid",
            str(exc),
            status_code=422,
            detail={"asset_id": asset_id},
        ) from exc

    reindex_asset(settings.catalog_db, settings.library_root, asset_id)
    return await library_asset(request, asset_id)


@router.get("/queue", response_model=QueueState)
async def get_queue(request: Request) -> QueueState:
    return _queue_state_model(await _playback(request).queue_snapshot())


@router.post("/queue", response_model=QueueState)
async def replace_queue(request: Request, payload: QueueReplaceRequest) -> QueueState:
    try:
        snapshot = await _playback(request).set_queue(
            _queue_specs(payload, _settings(request)),
            mode=payload.mode,
            command_id=str(payload.command_id) if payload.command_id else None,
        )
    except (PlaybackConflict, PlaybackOutputError, PlaybackError) as exc:
        raise _translate_playback_error(exc) from exc
    return _queue_state_model(snapshot)


@router.post("/queue/reorder", response_model=QueueState)
async def reorder_queue(request: Request, payload: QueueReorderRequest) -> QueueState:
    try:
        snapshot = await _playback(request).reorder(
            payload.asset_id,
            payload.to_index,
            command_id=str(payload.command_id) if payload.command_id else None,
        )
    except (PlaybackConflict, PlaybackOutputError, PlaybackError) as exc:
        raise _translate_playback_error(exc) from exc
    return _queue_state_model(snapshot)


@router.post("/queue/remove", response_model=QueueState)
async def remove_from_queue(request: Request, payload: QueueRemoveRequest) -> QueueState:
    try:
        snapshot = await _playback(request).remove(
            payload.asset_id,
            command_id=str(payload.command_id) if payload.command_id else None,
        )
    except (PlaybackConflict, PlaybackOutputError, PlaybackError) as exc:
        raise _translate_playback_error(exc) from exc
    return _queue_state_model(snapshot)


@router.post("/transport/{action}", response_model=PlaybackState)
async def transport(
    request: Request,
    action: str,
    payload: TransportCommand | None = None,
) -> PlaybackState:
    if action not in TRANSPORT_ACTIONS:
        raise ApiError(
            "transport_conflict",
            f"unknown transport action: {action}",
            status_code=422,
            detail={"allowed": list(TRANSPORT_ACTIONS)},
        )
    try:
        snapshot = await _playback(request).transport(
            action,  # type: ignore[arg-type]
            command_id=(str(payload.command_id) if payload and payload.command_id else None),
        )
    except (PlaybackConflict, PlaybackOutputError, PlaybackError) as exc:
        raise _translate_playback_error(exc) from exc
    return _playback_state_model(snapshot)


async def _snapshot_envelope(connection: Connection, *, seq: int) -> SnapshotEnvelope:
    playback_snapshot, queue_snapshot = await _playback(connection).snapshots()
    return SnapshotEnvelope(
        seq=seq,
        ts=_playback(connection).clock.utcnow().isoformat(),
        payload=SnapshotPayload(
            status=await _system_status(connection),
            playback=_playback_state_model(playback_snapshot),
            queue=_queue_state_model(queue_snapshot),
        ),
    )


def _event_envelope(event: Any) -> Any:
    common = {"seq": event.seq, "ts": event.ts}
    if event.type == "state.playback":
        return PlaybackEnvelope(
            **common,
            payload=PlaybackState.model_validate(event.payload),
        )
    if event.type == "state.queue":
        return QueueEnvelope(**common, payload=QueueState.model_validate(event.payload))
    if event.type == "state.devices":
        return DevicesEnvelope(**common, payload=OutputsState.model_validate(event.payload))
    if event.type == "state.library":
        return LibraryEnvelope(**common, payload=LibraryCounts.model_validate(event.payload))
    if event.type == "concierge.result":
        return ConciergeEnvelope(
            **common,
            payload=ConciergeResponse.model_validate(event.payload),
        )
    if event.type == "error":
        return ErrorEnvelope(**common, payload=ErrorBody.model_validate(event.payload))
    return ErrorEnvelope(
        **common,
        payload=ErrorBody(
            code="internal_error",
            message=f"Unknown server event type: {event.type}",
        ),
    )


@router.websocket("/ws")
async def state_socket(websocket: WebSocket) -> None:
    """Push authoritative snapshots and state deltas; clients never own playback."""
    await websocket.accept()
    playback = _playback(websocket)
    event_queue = playback.events.subscribe()
    receive_task: asyncio.Task[Any] | None = None
    event_task: asyncio.Task[Any] | None = None
    try:
        snapshot = await _snapshot_envelope(websocket, seq=playback.events.seq)
        await websocket.send_json(snapshot.model_dump(mode="json"))
        receive_task = asyncio.create_task(websocket.receive_json())
        event_task = asyncio.create_task(event_queue.get())

        while True:
            done, _ = await asyncio.wait(
                {receive_task, event_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if event_task in done:
                event = event_task.result()
                await websocket.send_json(_event_envelope(event).model_dump(mode="json"))
                event_task = asyncio.create_task(event_queue.get())

            if receive_task in done:
                message = receive_task.result()
                message_type = message.get("type") if isinstance(message, dict) else None
                if message_type == "state.request_snapshot":
                    snapshot = await _snapshot_envelope(websocket, seq=playback.events.seq)
                    await websocket.send_json(snapshot.model_dump(mode="json"))
                elif message_type == "ping":
                    pass
                else:
                    envelope = ErrorEnvelope(
                        seq=playback.events.seq,
                        ts=playback.clock.utcnow().isoformat(),
                        payload=ErrorBody(
                            code="request_invalid",
                            message="Unsupported WebSocket client message.",
                        ),
                    )
                    await websocket.send_json(envelope.model_dump(mode="json"))
                receive_task = asyncio.create_task(websocket.receive_json())
    except WebSocketDisconnect:
        pass
    finally:
        playback.events.unsubscribe(event_queue)
        for task in (receive_task, event_task):
            if task is not None and not task.done():
                task.cancel()
