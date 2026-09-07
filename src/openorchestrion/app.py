"""FastAPI application assembly.

Nothing here implements behaviour: routes live in :mod:`openorchestrion.api`,
and each of them delegates to an existing domain module. The application owns
configuration and wiring only.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .ai import MusicConcierge
from .ai_runtime import create_configured_concierge
from .api.errors import install_error_handlers
from .api.rendering_routes import router as rendering_router
from .api.routes import create_selection_executor, router
from .api.sessions import ConciergeSessions
from .api.settings import Settings
from .api.setup_routes import router as setup_router
from .api.web import install_web_app
from .midi.devices import list_output_ports
from .playback import PlaybackEngine
from .playback.factory import create_default_playback
from .playback.hotplug import AlsaOutputLinkProbe, OutputLinkMonitor


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Resolve application services once and keep playback server-owned."""
    if not hasattr(app.state, "settings"):
        app.state.settings = Settings.from_env()
    if not hasattr(app.state, "concierge"):
        app.state.concierge = create_configured_concierge(app.state.settings)
    if not hasattr(app.state, "concierge_sessions"):
        app.state.concierge_sessions = ConciergeSessions(app.state.concierge)
    app.state.selection_executor = create_selection_executor()
    production_playback = not hasattr(app.state, "playback")
    if production_playback:
        app.state.playback = create_default_playback(app.state.settings)
    # Physical outputs can vanish and return at any time; the monitor pauses
    # and resumes playback around that instead of playing into a dead port.
    monitor = OutputLinkMonitor(
        app.state.playback, AlsaOutputLinkProbe(),
        discover_ports=list_output_ports if production_playback else None,
    )
    await monitor.start()
    try:
        yield
    finally:
        await monitor.stop()
        try:
            await app.state.playback.close()
        finally:
            await asyncio.to_thread(
                app.state.selection_executor.shutdown, wait=True, cancel_futures=True
            )


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
    application.include_router(rendering_router)
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
