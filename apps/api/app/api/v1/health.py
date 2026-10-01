from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import text

from app.core.config import get_settings
from app.schemas.health import HealthOut, ReadyOut

router = APIRouter(tags=["health"])


@router.get("/healthz", response_model=HealthOut)
async def healthz() -> HealthOut:
    s = get_settings()
    return HealthOut(status="ok", name=s.app_name, version=s.app_version, env=s.app_env)


@router.get("/readyz", response_model=ReadyOut)
async def readyz(request: Request, response: Response) -> ReadyOut:
    checks: dict[str, bool] = {}
    try:
        async with request.app.state.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:
        checks["database"] = False
    try:
        checks.update(await request.app.state.adapters.health())
    except Exception:
        checks["adapters"] = False
    ok = all(checks.values())
    response.status_code = 200 if ok else 503
    return ReadyOut(status="ready" if ok else "degraded", checks=checks)


@router.get("/healthz/stream")
async def healthz_stream() -> StreamingResponse:
    """Diagnostic: six SSE ticks one second apart, so a proxy's streaming behaviour can be measured
    (a buffering proxy delivers them all at once after ~5 s)."""

    async def ticks() -> AsyncIterator[bytes]:
        for i in range(6):
            yield f'event: tick\ndata: {{"i": {i}, "t": {time.time():.3f}}}\n\n'.encode()
            await asyncio.sleep(1)

    return StreamingResponse(
        ticks(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
