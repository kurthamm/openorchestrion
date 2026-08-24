"""Readiness and harmless wizard-state endpoints for first-run setup."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from ..setup_state import (
    SETUP_VERSION,
    mark_setup_complete,
    read_setup_progress,
    reset_setup,
    setup_path,
)
from .models import AiState, LibraryCounts, OutputsState
from .routes import _system_status
from .settings import Settings

router = APIRouter(prefix="/api/setup", tags=["setup"])


class SetupStatus(BaseModel):
    """First-run guidance derived from authoritative appliance state."""

    model_config = ConfigDict(extra="forbid")

    wizard_version: int = SETUP_VERSION
    complete: bool
    completed_at: str | None = None
    marker_reason: str | None = None
    ready: bool
    ai: AiState
    outputs: OutputsState
    library: LibraryCounts
    next_steps: list[str] = Field(default_factory=list)


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _marker(settings: Settings) -> Path:
    # `history.db` is durable runtime state and lives directly under the
    # reference state root. Its parent is therefore the right durable boundary
    # for a tiny setup marker without putting it into the rebuildable library.
    return setup_path(settings.history_db.parent)


async def _status(request: Request) -> SetupStatus:
    system = await _system_status(request)
    concierge = request.app.state.concierge
    progress = read_setup_progress(_marker(_settings(request)))
    ready = bool(system.outputs.ready and system.library.indexed and system.library.assets > 0)

    next_steps: list[str] = []
    if not system.outputs.ready:
        next_steps.append(
            "Connect a MIDI output. For hardware-free diagnostics, enable virtual MIDI locally "
            "with openorchestrion-configure."
        )
    if not system.library.indexed:
        next_steps.append(
            "Import MIDI into the configured library and run openorchestrion-reindex."
        )
    elif system.library.assets == 0:
        next_steps.append("Import at least one MIDI asset into the configured library.")

    unavailable_reason = getattr(concierge, "unavailable_reason", None)
    ai = system.ai
    if unavailable_reason:
        ai = AiState(enabled=True, provider=ai.provider, reason=str(unavailable_reason))
        if "no_provider_configured" not in str(unavailable_reason):
            next_steps.append(
                "Hosted Concierge needs local administrator attention. Run "
                "openorchestrion-configure --show on the appliance."
            )

    if ready and not next_steps:
        next_steps.append("The core appliance is ready. Setup can be marked complete or revisited later.")

    return SetupStatus(
        complete=progress.complete,
        completed_at=progress.completed_at,
        marker_reason=progress.reason,
        ready=ready,
        ai=ai,
        outputs=system.outputs,
        library=system.library,
        next_steps=next_steps,
    )


@router.get("", response_model=SetupStatus)
async def setup_status(request: Request) -> SetupStatus:
    return await _status(request)


@router.post("/complete", response_model=SetupStatus)
async def setup_complete(request: Request) -> SetupStatus:
    # This is intentionally the only browser-write in setup: a harmless marker
    # under the durable state root. No request body, path, secret, hostname, or
    # system setting is accepted here.
    mark_setup_complete(_marker(_settings(request)))
    return await _status(request)


@router.post("/reset", response_model=SetupStatus)
async def setup_reset(request: Request) -> SetupStatus:
    reset_setup(_marker(_settings(request)))
    return await _status(request)


__all__ = ["SetupStatus", "router"]
