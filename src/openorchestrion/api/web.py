"""Static serving for the responsive web application.

Per ADR-0010 the UI ships as source: these files are served exactly as they
exist in the repository, with no build step. Per ADR-0005 the same application
serves the kiosk, phone, tablet, and desktop; the differences are layout, not
a second front end.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

WEB_ROOT = Path(__file__).resolve().parent.parent / "web"

# The appliance must work with no Internet, so nothing may be fetched from a
# third-party origin at runtime. This is enforced rather than merely intended.
_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'none'; "
    "form-action 'none'"
)


class _AppShell(StaticFiles):
    """Static files with a no-store index, so a kiosk never pins a stale shell."""

    async def get_response(self, path: str, scope: object) -> Response:
        response = await super().get_response(path, scope)  # type: ignore[arg-type]
        if path in {".", "index.html"}:
            response.headers["Cache-Control"] = "no-store"
        return response


def install_web_app(app: FastAPI) -> bool:
    """Mount the web application at ``/`` if its assets are present.

    Returns False when the directory is missing so an API-only deployment, or a
    test that only exercises JSON routes, still starts cleanly.
    """
    if not WEB_ROOT.is_dir():
        return False

    @app.middleware("http")
    async def _security_headers(request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        if not request.scope.get("path", "").startswith("/api"):
            response.headers.setdefault("Content-Security-Policy", _CSP)
            response.headers.setdefault("X-Content-Type-Options", "nosniff")
            response.headers.setdefault("Referrer-Policy", "same-origin")
        return response

    @app.get("/manifest.webmanifest", include_in_schema=False)
    async def manifest() -> FileResponse:
        return FileResponse(
            WEB_ROOT / "manifest.webmanifest",
            media_type="application/manifest+json",
        )

    app.mount("/", _AppShell(directory=WEB_ROOT, html=True), name="web")
    return True
