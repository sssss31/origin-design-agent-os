"""Uniform error envelope: {"error": {"code", "message", "details", "request_id"}}."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger

log = get_logger("errors")


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str | None = None, *, details: Any = None, code: str | None = None) -> None:
        self.message = message or self.code.replace("_", " ")
        self.details = details
        if code:
            self.code = code
        super().__init__(self.message)


class ValidationFailed(AppError):
    status_code = 422
    code = "validation_failed"


class Unauthorized(AppError):
    status_code = 401
    code = "unauthorized"


class Forbidden(AppError):
    status_code = 403
    code = "forbidden"


class NotFound(AppError):
    status_code = 404
    code = "not_found"


class Conflict(AppError):
    status_code = 409
    code = "conflict"


class RateLimited(AppError):
    status_code = 429
    code = "rate_limited"


class ServiceUnavailable(AppError):
    status_code = 503
    code = "service_unavailable"


def _envelope(request: Request, *, status: int, code: str, message: str, details: Any = None) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    body = {"error": {"code": code, "message": message, "details": details, "request_id": request_id}}
    headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
    return JSONResponse(status_code=status, content=body, headers=headers)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return _envelope(
            request, status=exc.status_code, code=exc.code, message=exc.message, details=exc.details
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        return _envelope(
            request,
            status=422,
            code="validation_failed",
            message="Request validation failed",
            details=jsonable_encoder(
                [{**e, "ctx": {k: str(v) for k, v in (e.get("ctx") or {}).items()}} for e in exc.errors()]
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {401: "unauthorized", 403: "forbidden", 404: "not_found", 405: "method_not_allowed"}.get(
            exc.status_code, "http_error"
        )
        return _envelope(request, status=exc.status_code, code=code, message=str(exc.detail))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_error", error_type=type(exc).__name__)
        return _envelope(request, status=500, code="internal_error", message="Internal server error")
