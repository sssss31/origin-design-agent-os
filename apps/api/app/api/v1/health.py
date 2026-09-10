from __future__ import annotations

from fastapi import APIRouter, Request, Response
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
