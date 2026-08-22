from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .models import ErrorBody, ErrorCode, ErrorResponse

logger = logging.getLogger("openorchestrion.api")

# Routes whose whole request body is a PlaybackIntent, so a validation failure
# there is an intent failure even though "intent" never appears in the path.
_INTENT_BODY_PATHS = frozenset({"/api/intent/validate"})


class ApiError(Exception):
    """Raised by handlers to produce the contract's single error envelope."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        status_code: int = 400,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code: ErrorCode = code
        self.message = message
        self.status_code = status_code
        self.detail = detail


def _envelope(code: ErrorCode, message: str, detail: dict[str, Any] | None = None) -> dict[str, Any]:
    return ErrorResponse(error=ErrorBody(code=code, message=message, detail=detail)).model_dump()


def _validation_code(request: Request, errors: list[Any]) -> ErrorCode:
    """Distinguish a bad intent from any other bad request.

    ``intent_invalid`` lets the UI point its Concierge surface at the offending
    field; a malformed query parameter or queue command is not that, and saying
    so would send the user to the wrong screen.
    """
    if request.scope.get("path") in _INTENT_BODY_PATHS:
        return "intent_invalid"
    for error in errors:
        if "intent" in tuple(str(part) for part in error.get("loc", ())):
            return "intent_invalid"
    return "request_invalid"


def install_error_handlers(app: FastAPI) -> None:
    """Route every failure through the contract envelope.

    The catch-all matters as much as the specific handlers: without it an
    unexpected exception reaches the client as a framework HTML 500, which a
    7-inch touchscreen has no way to render.
    """

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.code, exc.message, exc.detail),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = exc.errors()
        first = errors[0] if errors else {}
        location = [str(part) for part in first.get("loc", ())]
        return JSONResponse(
            status_code=422,
            content=_envelope(
                _validation_code(request, errors),
                first.get("msg", "request payload failed validation"),
                {"field": ".".join(location), "errors": len(errors)},
            ),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Log the real cause server-side; return nothing about it to the client.
        logger.exception(
            "unhandled error serving %s %s",
            request.scope.get("method", "?"),
            request.scope.get("path", "?"),
            exc_info=exc,
        )
        return JSONResponse(
            status_code=500,
            content=_envelope(
                "internal_error",
                "The appliance hit an unexpected error. Check the server log.",
            ),
        )
