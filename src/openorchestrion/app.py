"""FastAPI application assembly.

Nothing here implements behaviour: routes live in :mod:`openorchestrion.api`,
and each of them delegates to an existing domain module. The application owns
configuration and wiring only.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from .ai import MusicConcierge
from .ai_runtime import create_configured_concierge
from .api.errors import install_error_handlers
from .api.routes import router
from .api.sessions import ConciergeSessions
from .api.settings import Settings
from .api.setup_routes import router as setup_router
from .api.web import install_web_app
from .playback import PlaybackEngine
from .playback.factory import create_default_playback


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Resolve application services once and keep playback server-owned."""
    if not hasattr(app.state, "settings"):
        app.state.settings = Settings.from_env()
    if not hasattr(app.state, "concierge"):
        app.state.concierge = create_configured_concierge(app.state.settings)
    if not hasattr(app.state, "concierge_sessions"):
        app.state.concierge_sessions = ConciergeSessions(app.state.concierge)
    if not hasattr(app.state, "playback"):
        app.state.playback = create_default_playback(app.state.settings)
    try:
        yield
    finally:
        # A service restart is a real playback interruption. Finish the durable
        # history attempt before closing ports so it cannot remain "started"
        # forever after an orderly shutdown.
        with suppress(Exception):
            snapshot = await app.state.playback.playback_snapshot()
            if snapshot.state in {"playing", "paused"}:
                await app.state.playback.transport("stop")
        await app.state.playback.close()


def create_app(
    *,
    settings: Settings | None = None,
    concierge: MusicConcierge | None = None,
    playback: PlaybackEngine | None = None,
) -> FastAPI:
    """Build an application instance with injectable services for tests."""
    application = FastAPI(
        title="OpenOrchestrion",
        description="Networked MIDI music appliance",
        version="0.1.0-dev",
        lifespan=lifespan,
    )
    install_error_handlers(application)
    application.include_router(router)
    application.include_router(setup_router)
    # Mounted last: the catch-all static mount at "/" must not shadow /api.
    install_web_app(application)
    if settings is not None:
        application.state.settings = settings
    if concierge is not None:
        application.state.concierge = concierge
        application.state.concierge_sessions = ConciergeSessions(concierge)
    if playback is not None:
        application.state.playback = playback
    return application


app = create_app()
