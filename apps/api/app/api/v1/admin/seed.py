"""Seed the eight design agents from the console (spec §16 P6) — idempotent."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.v1.admin import AdminAuth
from app.core.authz import DB
from app.seeds.design_agents import seed_design_agents

router = APIRouter()


class SeedRequest(BaseModel):
    provider_type: Literal["openai", "echo"] = "openai"
    model: str | None = None
    publish: bool = True


class SeedResult(BaseModel):
    tools: int
    skills: int
    agents: int
    published: int
    skipped: int = 0


@router.post("/seed/design-agents", response_model=SeedResult)
async def seed(body: SeedRequest, ctx: AdminAuth, session: DB) -> SeedResult:
    stats = await seed_design_agents(
        session, ctx, provider_type=body.provider_type, model=body.model, publish=body.publish
    )
    return SeedResult(**stats)
