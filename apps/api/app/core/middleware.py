"""Request-context middleware: request id + timing, bound into structured logs."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from starlette.datastructures import Headers, MutableHeaders

from app.core.logging import get_logger

log = get_logger("http")
ASGIApp = Callable[
    [dict[str, Any], Callable[[], Awaitable[dict[str, Any]]], Callable[[dict[str, Any]], Awaitable[None]]],
    Awaitable[None],
]


class RequestContextMiddleware:
    """Pure ASGI middleware so streaming (SSE) responses are not buffered."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        request_id = headers.get("x-request-id") or uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id, method=scope["method"], path=scope["path"]
        )
        started = time.perf_counter()
        status_holder = {"status": 0}

        async def send_wrapper(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                MutableHeaders(scope=message).append("x-request-id", request_id)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            if not scope["path"].endswith(("/healthz", "/readyz")):
                log.info("request", status=status_holder["status"], duration_ms=duration_ms)
            structlog.contextvars.clear_contextvars()


class EnsureStartedMiddleware:
    """Serverless hosts (Vercel Functions) may never send ASGI lifespan events; run the app's
    startup on the first request instead, exactly once per process."""

    def __init__(self, app: ASGIApp, startup: Callable[[Any], Awaitable[None]]) -> None:
        self.app = app
        self._startup = startup
        self._lock: asyncio.Lock | None = None

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] in ("http", "websocket"):
            app = scope.get("app")
            if app is not None and not getattr(app.state, "ready", False):
                if self._lock is None:
                    self._lock = asyncio.Lock()
                async with self._lock:
                    if not getattr(app.state, "ready", False):
                        await self._startup(app)
        await self.app(scope, receive, send)
