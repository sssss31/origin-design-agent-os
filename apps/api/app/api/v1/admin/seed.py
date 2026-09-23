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


REGISTRY = [
    ("/master", "Master Design Agent", "Create master design"),
    ("/resize", "Resize Agent", "Resize existing design"),
    ("/editable", "Editable Design Agent", "Convert design to editable format"),
    ("/qc", "Design QC Agent", "Check design quality"),
    ("/copy", "Copy Agent", "Content/copy work"),
    ("/asset", "Asset Agent", "Find and prepare assets"),
    ("/export", "Export Agent", "Export final files"),
    ("/agent8", "Existing Agent 8", "Eighth existing agent"),
]


class RegistrySeedRequest(BaseModel):
    connection_type: Literal["openai_responses", "http"] = "openai_responses"


class RegistrySeedResult(BaseModel):
    created: int
    skipped: int
    commands: list[str]


@router.post("/seed/agent-registry", response_model=RegistrySeedResult)
async def seed_registry(body: RegistrySeedRequest, ctx: AdminAuth, session: DB) -> RegistrySeedResult:
    """Workspace V0 §2: the eight registry entries as editable rows (connection added per agent)."""
    from app.schemas.admin import AgentCreate
    from app.services.agents import AgentService

    svc = AgentService(session, ctx)
    existing = {a.command for a in await svc.list()}
    created = skipped = 0
    for command, name, description in REGISTRY:
        if command in existing:
            skipped += 1
            continue
        agent = await svc.create(AgentCreate(name=name, command=command, description=description))
        agent.connection_type = body.connection_type
        created += 1
    await session.flush()
    return RegistrySeedResult(created=created, skipped=skipped, commands=[c for c, _, _ in REGISTRY])


@router.post("/seed/design-agents", response_model=SeedResult)
async def seed(body: SeedRequest, ctx: AdminAuth, session: DB) -> SeedResult:
    stats = await seed_design_agents(
        session, ctx, provider_type=body.provider_type, model=body.model, publish=body.publish
    )
    return SeedResult(**stats)
