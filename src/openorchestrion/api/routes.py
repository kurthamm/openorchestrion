"""HTTP and WebSocket surface for the OpenOrchestrion application."""

from __future__ import annotations

import asyncio
import json
import multiprocessing
import shutil
import sqlite3
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from dataclasses import replace
from functools import partial
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Request, WebSocket, WebSocketDisconnect

from ..ai import ConciergeResult, MusicConcierge
from ..history import apply_no_repeat_window
from ..library.browse import browse, browse_facets, performance_detail
from ..library.catalog import (
    catalog_facets,
    catalog_stats,
    get_asset,
    reindex_asset,
    search_catalog,
)
from ..library.metadata import (
    AssetNotFoundError,
    MetadataConflictError,
    MetadataError,
    set_favorite,
    sidecar_path,
)
from ..library.readiness import readiness, source_facts
from ..library.qualification import qualification
from ..models import PlaybackIntent
from ..playback import (
    PlaybackConflict,
    PlaybackEngine,
    PlaybackError,
    PlaybackOutputError,
    QueueItemSpec,
    RenderingMode,
    RenderingPolicy,
)
from ..playback.voicing import suggest_program_overrides
from ..player_state import PlayerStateStore
from ..stations import StationConstraints, build_station
from .errors import ApiError
from .listening_models import (
    BrowseFacets,
    BrowsePage,
    PerformanceDetail,
    PerformancePreview,
    PerformancePreviewRequest,
)
from .models import (
    TRANSPORT_ACTIONS,
    AiState,
    BackupHealth,
    CollectionCreateRequest,
    CollectionRenameRequest,
    CollectionsResponse,
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
    LibraryFacets,
    LibrarySearchResponse,
    OperationsStatus,
    OutputsState,
    PlaybackEnvelope,
    PlaybackModesRequest,
    PlaybackState,
    QueueBulkRemoveRequest,
    QueueEnvelope,
    QueueRemoveRequest,
    QueueReorderRequest,
    QueueReplaceRequest,
    QueueState,
    SavedCollectionModel,
    ScheduleStartRequest,
    SeekRequest,
    SleepTimerRequest,
    SnapshotEnvelope,
    SnapshotPayload,
    SongPreference,
    SongPreferenceRequest,
    StationPreviewRequest,
    StationQueueModel,
    SystemStatus,
    TestNoteRequest,
    TransportCommand,
    VolumeCommand,
)
from .sessions import ConciergeSessions
from .settings import Settings

router = APIRouter(prefix="/api")
_STARTED_AT = time.monotonic()
Connection = Request | WebSocket


@router.get('/library/browse', response_model=BrowsePage)
async def listening_library(
    request: Request, text: str = Query('', max_length=200),
    genre: str = '', mood: str = '', era: str = '', composer: str = '',
    source: str = '', arrangement: str = '', favorite: bool = False,
    sort: Literal['title', 'composer', 'duration', 'newest'] = 'title',
    offset: int = Query(0, ge=0), limit: int = Query(40, ge=1, le=100),
) -> dict[str, Any]:
    return await asyncio.to_thread(
        browse, _require_catalog(_settings(request)), text=text, genre=genre, mood=mood,
        era=era, composer=composer, source=source, arrangement=arrangement,
        favorite=favorite, sort=sort, offset=offset, limit=limit,
    )


@router.get('/library/browse/facets', response_model=BrowseFacets)
async def listening_facets(request: Request) -> dict[str, Any]:
    return await asyncio.to_thread(browse_facets, _require_catalog(_settings(request)))


@router.get('/library/assets/{asset_id}/performance', response_model=PerformanceDetail)
async def listening_performance(request: Request, asset_id: str) -> dict[str, Any]:
    result = await asyncio.to_thread(performance_detail, _require_catalog(_settings(request)), asset_id)
    if result is None:
        raise ApiError('asset_not_found', 'This performance is no longer in the listening library.', status_code=404)
    return result


def _performance_preview(settings: Settings, asset_id: str, payload: PerformancePreviewRequest) -> dict:
    # The same resolver used by queue creation includes automatic voicing.
    spec = _queue_specs(QueueReplaceRequest(asset_ids=[asset_id], rendering=payload.rendering), settings)[0]
    try:
        facts = source_facts(settings.catalog_db, asset_id, str(spec.midi_path))
    except (OSError, ValueError) as exc:
        raise ApiError("analysis_unavailable", "Playback facts could not be verified for this file.", status_code=409) from exc
    return {"rendering_mode": payload.rendering.mode.value if payload.rendering else "AUTO",
            "qualification": qualification(settings.catalog_db, asset_id),
            "readiness": readiness(facts, spec.performance_type, spec.rendering_policy)}


@router.post('/library/assets/{asset_id}/performance/preview', response_model=PerformancePreview)
async def listening_preview(request: Request, asset_id: str, payload: PerformancePreviewRequest) -> dict:
    return await _selection(request, _performance_preview, _settings(request), asset_id, payload)


def _settings(connection: Connection) -> Settings:
    return connection.app.state.settings


def _concierge(connection: Connection) -> MusicConcierge:
    return connection.app.state.concierge


def _sessions(request: Request) -> ConciergeSessions:
    return request.app.state.concierge_sessions


def _playback(connection: Connection) -> PlaybackEngine:
    return connection.app.state.playback


def _player_store(connection: Connection) -> PlayerStateStore:
    path = _settings(connection).player_state_db
    if path is None:
        raise ApiError("internal_error", "Player state storage is not configured.", status_code=503)
    return PlayerStateStore(path)


def _outputs_state(connection: Connection) -> OutputsState:
    return OutputsState.model_validate(_playback(connection).outputs_state())


def create_selection_executor() -> ProcessPoolExecutor:
    return ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("spawn"))


async def _selection(connection: Connection, function: Any, *args: Any, **kwargs: Any) -> Any:
    """CPU-heavy selection has a separate process, never a second MIDI owner."""
    executor = connection.app.state.selection_executor
    try:
        return await asyncio.get_running_loop().run_in_executor(
            executor, partial(function, *args, **kwargs)
        )
    except BrokenProcessPool as exc:
        if connection.app.state.selection_executor is executor:
            connection.app.state.selection_executor = create_selection_executor()
            await asyncio.to_thread(executor.shutdown, wait=True, cancel_futures=True)
        raise ApiError(
            "internal_error", "Selection worker stopped. Retry the request.", status_code=503
        ) from exc


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
    library = await asyncio.to_thread(_library_counts, settings.catalog_db)
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


def _asset_spec(
    record: dict[str, Any],
    settings: Settings,
    *,
    intent: PlaybackIntent | None = None,
    rendering_policy: RenderingPolicy | None = None,
) -> QueueItemSpec:
    """Translate catalog data and validated request hints into a playback item.

    The API does not make routing or rendering decisions. It carries curated
    performance type, validated device/role preferences, and an already-validated
    ephemeral rendering policy to the playback engine. Untagged assets therefore
    keep ``performance_type=None`` and fall back to MIDI/GM analysis in the
    planner, while omitted rendering preserves the source arrangement exactly.
    """
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
        performance_type=record.get("performance_type"),
        device_preferences=tuple(intent.device_preferences) if intent else (),
        routing_preferences=dict(intent.routing_preferences) if intent else {},
        rendering_policy=rendering_policy,
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


def _build_station(settings: Settings, intent: PlaybackIntent, **kwargs: Any) -> Any:
    """Run selection and its history reads together outside the MIDI event loop."""
    return build_station(
        _require_catalog(settings), intent,
        constraints=_station_constraints(settings, intent), **kwargs,
    )


def _default_rendering_policy(settings: Settings, record: dict[str, Any]) -> RenderingPolicy | None:
    """Voicing correction applied when a queue request names no rendering.

    Orchestral score exports routinely carry poor General MIDI choices (solo
    string patches on whole sections, no Program Change at all). The stored
    deterministic analysis is enough to correct them; solo, duet and chamber
    files produce no suggestion and keep their source arrangement exactly.
    Passing ``rendering.mode = "ORIGINAL"`` explicitly disables this.
    """
    with sidecar_path(settings.library_root, record["asset_id"]).open("r", encoding="utf-8") as fh:
        analysis = json.load(fh)["deterministic_analysis"]
    overrides = suggest_program_overrides(analysis)
    if not overrides:
        return None
    return RenderingPolicy.from_values(mode=RenderingMode.OVERRIDE, program_overrides=overrides)


def _queue_specs(payload: QueueReplaceRequest, settings: Settings) -> list[QueueItemSpec]:
    catalog_db = _require_catalog(settings)
    rendering_policy = payload.rendering.to_policy() if payload.rendering is not None else None

    def policy_for(record: dict[str, Any]) -> RenderingPolicy | None:
        if payload.rendering is not None:
            return rendering_policy
        return _default_rendering_policy(settings, record)

    def with_preference(spec: QueueItemSpec) -> QueueItemSpec:
        if settings.player_state_db is None:
            return spec
        preference = PlayerStateStore(settings.player_state_db).get_song_preference(spec.asset_id)
        if preference is None:
            return spec
        saved_rendering = preference.get("rendering")
        policy = spec.rendering_policy
        if payload.rendering is None and saved_rendering:
            from .models import RenderingRequest
            policy = RenderingRequest.model_validate(saved_rendering).to_policy()
        return replace(spec, tempo_percent=preference["tempo_percent"],
                       volume_percent=preference["volume_percent"], rendering_policy=policy)
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
            # Station selection already chose the asset. Re-read its catalog row
            # here so playback receives the curated performance_type without
            # widening the public StationQueue response model.
            record = get_asset(catalog_db, item.asset_id)
            if record is None:
                raise ApiError(
                    "asset_not_found",
                    f"selected station asset disappeared from the catalog: {item.asset_id}",
                    status_code=404,
                    detail={"asset_id": item.asset_id},
                )
            specs.append(
                with_preference(_asset_spec(
                    record,
                    settings,
                    intent=payload.intent,
                    rendering_policy=policy_for(record),
                ))
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
        specs.append(with_preference(_asset_spec(record, settings, rendering_policy=policy_for(record))))
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


@router.post("/devices/test-note", status_code=204)
async def test_note(request: Request, payload: TestNoteRequest) -> None:
    try:
        await _playback(request).test_note(note=payload.note, velocity=payload.velocity,
                                           duration_seconds=payload.duration_seconds)
    except (PlaybackConflict, PlaybackOutputError, PlaybackError) as exc:
        raise _translate_playback_error(exc) from exc


@router.get("/operations", response_model=OperationsStatus)
async def operations(request: Request) -> OperationsStatus:
    settings = _settings(request)
    usage = shutil.disk_usage(settings.library_root)
    playback, queue = await _playback(request).snapshots()
    backup = None
    backup_path = settings.history_db.parent / "backup-status.json"
    if backup_path.is_file():
        try:
            backup = BackupHealth.model_validate(json.loads(backup_path.read_text(encoding="utf-8")))
        except (OSError, ValueError, json.JSONDecodeError):
            backup = BackupHealth(status="unreadable")
    try:
        installed_version = version("openorchestrion")
    except PackageNotFoundError:
        installed_version = "development"
    system = await _system_status(request)
    if shutil.which("cloudflared"):
        try:
            result = await asyncio.to_thread(
                subprocess.run, ["systemctl", "is-active", "cloudflared.service"],
                capture_output=True, text=True, timeout=2, check=False,
            )
            tunnel_status = "active" if result.returncode == 0 else "inactive"
        except (OSError, subprocess.SubprocessError):
            tunnel_status = "unknown"
    else:
        tunnel_status = "not_configured"
    return OperationsStatus(
        service_version=installed_version, uptime_seconds=round(time.monotonic() - _STARTED_AT),
        disk_free_bytes=usage.free, disk_total_bytes=usage.total, queue_length=len(queue.items),
        playback_state=playback.state, outputs=_outputs_state(request), backup=backup,
        library_indexed=system.library.indexed, library_assets=system.library.assets,
        tunnel_status=tunnel_status, recent_playback_failures=list(_playback(request).recent_failures),
    )


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
            await _selection(
                request,
                _build_station,
                settings,
                result.intent,
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
    queue = await _selection(
        request,
        _build_station,
        settings,
        payload.intent,
        seed=payload.seed,
        max_tracks=payload.max_tracks,
    )
    return _station_queue_model(queue)


@router.post("/intent/validate", response_model=PlaybackIntent)
async def validate_intent(intent: PlaybackIntent) -> PlaybackIntent:
    return intent


@router.get("/library/stats", response_model=LibraryCounts)
async def library_stats(request: Request) -> LibraryCounts:
    return await asyncio.to_thread(_library_counts, _settings(request).catalog_db)


@router.get("/library/facets", response_model=LibraryFacets)
async def library_facets(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=500)] = 40,
) -> LibraryFacets:
    settings = _settings(request)
    if not settings.catalog_db.is_file():
        return LibraryFacets(indexed=False)
    facets = await asyncio.to_thread(catalog_facets, settings.catalog_db, limit=limit)
    return LibraryFacets(indexed=True, **facets)


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
    rows = await asyncio.to_thread(
        search_catalog,
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

    summaries = list(reversed(await asyncio.to_thread(history_summaries, settings.history_db)))[:limit]
    items = [HistoryEntry.model_validate(summary.to_dict()) for summary in summaries]
    return HistoryResponse(items=items, count=len(items))


@router.get(
    "/library/assets/{asset_id}",
    response_model=LibraryAssetDetail,
    responses={404: {"model": ErrorResponse, "description": "No such asset in the catalog"}},
)
async def library_asset(request: Request, asset_id: str) -> LibraryAssetDetail:
    settings = _settings(request)
    record = (
        await asyncio.to_thread(get_asset, settings.catalog_db, asset_id)
        if settings.catalog_db.is_file() else None
    )
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
        await asyncio.to_thread(set_favorite, settings.library_root, asset_id, payload.favorite)
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

    await asyncio.to_thread(reindex_asset, settings.catalog_db, settings.library_root, asset_id)
    return await library_asset(request, asset_id)


@router.get("/queue", response_model=QueueState)
async def get_queue(request: Request) -> QueueState:
    return _queue_state_model(await _playback(request).queue_snapshot())


@router.post("/queue", response_model=QueueState)
async def replace_queue(request: Request, payload: QueueReplaceRequest) -> QueueState:
    try:
        specs = await _selection(request, _queue_specs, payload, _settings(request))
        snapshot = await _playback(request).set_queue(
            specs,
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


@router.post("/queue/clear", response_model=QueueState)
async def clear_queue(request: Request, payload: TransportCommand) -> QueueState:
    try:
        snapshot = await _playback(request).clear_queue(
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


@router.post("/queue/remove-many", response_model=QueueState)
async def remove_many_from_queue(request: Request, payload: QueueBulkRemoveRequest) -> QueueState:
    try:
        return _queue_state_model(await _playback(request).remove_many(payload.asset_ids))
    except (PlaybackConflict, PlaybackOutputError, PlaybackError) as exc:
        raise _translate_playback_error(exc) from exc


@router.post("/queue/play-next", response_model=QueueState)
async def queue_play_next(request: Request, payload: QueueRemoveRequest) -> QueueState:
    try:
        return _queue_state_model(await _playback(request).play_next(payload.asset_id))
    except (PlaybackConflict, PlaybackOutputError, PlaybackError) as exc:
        raise _translate_playback_error(exc) from exc


@router.post("/queue/undo", response_model=QueueState)
async def undo_queue(request: Request) -> QueueState:
    try:
        return _queue_state_model(await _playback(request).undo_queue())
    except PlaybackConflict as exc:
        raise _translate_playback_error(exc) from exc


@router.post("/playback/modes", response_model=QueueState)
async def playback_modes(request: Request, payload: PlaybackModesRequest) -> QueueState:
    return _queue_state_model(await _playback(request).set_modes(
        repeat_mode=payload.repeat_mode, shuffle=payload.shuffle, continuous=payload.continuous,
    ))


@router.post("/playback/seek", response_model=PlaybackState)
async def playback_seek(request: Request, payload: SeekRequest) -> PlaybackState:
    try:
        return _playback_state_model(await _playback(request).seek(payload.position_seconds))
    except (PlaybackConflict, PlaybackOutputError, PlaybackError) as exc:
        raise _translate_playback_error(exc) from exc


@router.post("/playback/sleep-timer", response_model=PlaybackState)
async def playback_sleep_timer(request: Request, payload: SleepTimerRequest) -> PlaybackState:
    return _playback_state_model(await _playback(request).set_sleep_timer(
        payload.seconds, after_current=payload.after_current,
    ))


@router.post("/playback/schedule-start", response_model=PlaybackState)
async def schedule_start(request: Request, payload: ScheduleStartRequest) -> PlaybackState:
    try:
        return _playback_state_model(await _playback(request).schedule_start(payload.seconds))
    except (PlaybackConflict, PlaybackOutputError, PlaybackError) as exc:
        raise _translate_playback_error(exc) from exc


def _collection_model(value: Any) -> SavedCollectionModel:
    return SavedCollectionModel.model_validate(value.to_dict())


@router.get("/collections", response_model=CollectionsResponse)
async def collections(request: Request) -> CollectionsResponse:
    values = await asyncio.to_thread(_player_store(request).list_collections)
    return CollectionsResponse(items=[_collection_model(value) for value in values])


@router.post("/collections", response_model=SavedCollectionModel)
async def save_collection(request: Request, payload: CollectionCreateRequest) -> SavedCollectionModel:
    asset_ids = payload.asset_ids
    if payload.kind == "playlist" and not asset_ids:
        queue = await _playback(request).queue_snapshot()
        asset_ids = [item.asset_id for item in queue.items]
    try:
        value = await asyncio.to_thread(
            _player_store(request).save_collection,
            name=payload.name, kind=payload.kind, asset_ids=asset_ids,
            intent=payload.intent.model_dump(mode="json") if payload.intent else None,
        )
    except (ValueError, sqlite3.IntegrityError) as exc:
        raise ApiError("request_invalid", str(exc), status_code=409) from exc
    return _collection_model(value)


@router.post("/collections/{collection_id}/load", response_model=QueueState)
async def load_collection(request: Request, collection_id: str) -> QueueState:
    value = await asyncio.to_thread(_player_store(request).get_collection, collection_id)
    if value is None:
        raise ApiError("asset_not_found", "Saved collection was not found.", status_code=404)
    payload = QueueReplaceRequest(
        asset_ids=list(value.asset_ids),
        intent=PlaybackIntent.model_validate(value.intent) if value.intent else None,
    )
    specs = await _selection(request, _queue_specs, payload, _settings(request))
    return _queue_state_model(await _playback(request).set_queue(specs))


@router.patch("/collections/{collection_id}", response_model=SavedCollectionModel)
async def rename_collection(request: Request, collection_id: str, payload: CollectionRenameRequest) -> SavedCollectionModel:
    try:
        value = await asyncio.to_thread(_player_store(request).rename_collection, collection_id, payload.name)
    except (ValueError, sqlite3.IntegrityError) as exc:
        raise ApiError("request_invalid", str(exc), status_code=409) from exc
    if value is None:
        raise ApiError("asset_not_found", "Saved collection was not found.", status_code=404)
    return _collection_model(value)


@router.delete("/collections/{collection_id}", status_code=204)
async def delete_collection(request: Request, collection_id: str) -> None:
    if not await asyncio.to_thread(_player_store(request).delete_collection, collection_id):
        raise ApiError("asset_not_found", "Saved collection was not found.", status_code=404)


@router.get("/library/assets/{asset_id}/preference", response_model=SongPreference | None)
async def song_preference(request: Request, asset_id: str) -> SongPreference | None:
    value = await asyncio.to_thread(_player_store(request).get_song_preference, asset_id)
    return SongPreference.model_validate(value) if value else None


@router.put("/library/assets/{asset_id}/preference", response_model=SongPreference)
async def save_song_preference(request: Request, asset_id: str,
                               payload: SongPreferenceRequest) -> SongPreference:
    if get_asset(_require_catalog(_settings(request)), asset_id) is None:
        raise ApiError("asset_not_found", "Performance was not found.", status_code=404)
    value = await asyncio.to_thread(
        _player_store(request).save_song_preference, asset_id,
        tempo_percent=payload.tempo_percent, volume_percent=payload.volume_percent,
        rendering=payload.rendering.model_dump(mode="json") if payload.rendering else None,
    )
    return SongPreference.model_validate(value)


@router.delete("/library/assets/{asset_id}/preference", status_code=204)
async def delete_song_preference(request: Request, asset_id: str) -> None:
    await asyncio.to_thread(_player_store(request).delete_song_preference, asset_id)


@router.post("/volume", response_model=PlaybackState)
async def volume(request: Request, payload: VolumeCommand) -> PlaybackState:
    try:
        snapshot = await _playback(request).set_volume(
            payload.level,
            command_id=str(payload.command_id) if payload.command_id else None,
        )
    except (PlaybackConflict, PlaybackOutputError, PlaybackError) as exc:
        raise _translate_playback_error(exc) from exc
    return _playback_state_model(snapshot)


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
