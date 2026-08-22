"""FastAPI application assembly.

Nothing here implements behaviour: routes live in :mod:`openorchestrion.api`,
and each of them delegates to an existing domain module. The application owns
configuration and wiring only.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .ai import MusicConcierge
from .api.errors import install_error_handlers
from .api.routes import router
from .api.sessions import ConciergeSessions
from .api.settings import Settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Resolve configuration once so handlers never read the environment.

    Values injected by :func:`create_app` win: startup fills in what is missing
    rather than replacing what a caller already supplied.
    """
    if not hasattr(app.state, "settings"):
        app.state.settings = Settings.from_env()
    if not hasattr(app.state, "concierge"):
        # No primary provider configured: MusicConcierge falls back to the
        # offline deterministic interpreter, so natural language keeps working
        # without a network or an API key.
        app.state.concierge = MusicConcierge()
    if not hasattr(app.state, "concierge_sessions"):
        app.state.concierge_sessions = ConciergeSessions(app.state.concierge)
    yield


def create_app(
    *,
    settings: Settings | None = None,
    concierge: MusicConcierge | None = None,
) -> FastAPI:
    """Build an application instance.

    Tests pass explicit dependencies; production uses the lifespan defaults.
    """
    application = FastAPI(
        title="OpenOrchestrion",
        description="Networked MIDI music appliance",
        version="0.1.0-dev",
        lifespan=lifespan,
    )
    install_error_handlers(application)
    application.include_router(router)
    if settings is not None:
        application.state.settings = settings
    if concierge is not None:
        application.state.concierge = concierge
        application.state.concierge_sessions = ConciergeSessions(concierge)
    return application


app = create_app()
