from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .models import ErrorBody, ErrorCode, ErrorResponse


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


def install_error_handlers(app: FastAPI) -> None:
    """Route every failure through the contract envelope.

    Pydantic rejects unknown fields on PlaybackIntent, so malformed intents are
    a routine client error rather than a server fault; they must still arrive as
    something the touchscreen can render.
    """

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.code, exc.message, exc.detail),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = exc.errors()
        first = errors[0] if errors else {}
        location = [str(part) for part in first.get("loc", ())]
        return JSONResponse(
            status_code=422,
            content=_envelope(
                "intent_invalid",
                first.get("msg", "request payload failed validation"),
                {"field": ".".join(location), "errors": len(errors)},
            ),
        )
