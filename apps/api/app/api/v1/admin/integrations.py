"""Admin → API Integrations: one overview for provider cards (OpenAI, …) and custom REST APIs."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.v1.admin import AdminAuth
from app.core.authz import DB
from app.core.deps import AdaptersDep
from app.models.agents import Agent, AgentVersion
from app.models.workflows import ApiUsage
from app.schemas.admin import ProviderOut
from app.services.admin_serializers import provider_out
from app.services.providers import ProviderService

router = APIRouter(prefix="/integrations")


class ProviderCard(BaseModel):
    provider: ProviderOut
    used_by: list[str] = Field(default_factory=list)
    requests_month: int = 0
    tokens_month: int = 0
    avg_latency_ms: int | None = None
    estimated_cost_month_usd: float | None = None


class ProviderTypeInfo(BaseModel):
    type: str
    display_name: str
    supported_models: list[dict] = Field(default_factory=list)


class IntegrationsOverview(BaseModel):
    provider_types: list[ProviderTypeInfo]
    providers: list[ProviderCard]
    custom: list[dict] = Field(default_factory=list)


@router.get("/overview", response_model=IntegrationsOverview)
async def overview(ctx: AdminAuth, session: DB, adapters: AdaptersDep) -> IntegrationsOverview:
    org = ctx.require_organization()
    month_start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    svc = ProviderService(session, ctx)
    providers = await svc.list()
    usage_rows = (
        await session.execute(
            select(
                ApiUsage.provider_type,
                func.count(ApiUsage.id),
                func.coalesce(func.sum(ApiUsage.input_tokens + ApiUsage.output_tokens), 0),
                func.coalesce(func.avg(ApiUsage.duration_ms), 0),
            )
            .where(ApiUsage.organization_id == org, ApiUsage.created_at >= month_start)
            .group_by(ApiUsage.provider_type)
        )
    ).all()
    usage = {row[0]: row for row in usage_rows}
    used_by_rows = (
        await session.execute(
            select(AgentVersion.provider_id, Agent.name)
            .join(Agent, Agent.id == AgentVersion.agent_id)
            .where(Agent.organization_id == org, Agent.active_version_id == AgentVersion.id)
        )
    ).all()
    used_by: dict[uuid.UUID, list[str]] = {}
    for provider_id, name in used_by_rows:
        if provider_id:
            used_by.setdefault(provider_id, []).append(name)
    cards = []
    for p in providers:
        u = usage.get(p.type)
        cards.append(
            ProviderCard(
                provider=provider_out(p),
                used_by=sorted(used_by.get(p.id, [])),
                requests_month=int(u[1]) if u else 0,
                tokens_month=int(u[2]) if u else 0,
                avg_latency_ms=int(u[3]) if u and u[1] else None,
            )
        )
    types = [
        ProviderTypeInfo(type=t, display_name=a.display_name, supported_models=a.get_supported_models())
        for t, a in adapters.providers.items()
    ]
    return IntegrationsOverview(provider_types=types, providers=cards, custom=[])
