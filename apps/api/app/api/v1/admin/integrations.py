"""Admin → API Integrations: one overview for provider cards (OpenAI, …) and custom REST APIs."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.admin import AdminAuth
from app.core.authz import DB, AuthContext, Config
from app.core.config import Settings
from app.core.deps import AdaptersDep
from app.models.agents import Agent, AgentVersion
from app.models.workflows import ApiUsage
from app.schemas.admin import ProviderOut
from app.schemas.integrations import (
    CurlImportIn,
    CurlParseIn,
    CurlPreview,
    IntegrationCreate,
    IntegrationOut,
    IntegrationSecretIn,
    IntegrationTestIn,
    IntegrationTestOut,
    IntegrationUpdate,
)
from app.services.admin_serializers import integration_out, provider_out
from app.services.integrations import IntegrationService
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
    custom: list[IntegrationOut] = Field(default_factory=list)


@router.get("/overview", response_model=IntegrationsOverview)
async def overview(
    ctx: AdminAuth, session: DB, adapters: AdaptersDep, settings: Config
) -> IntegrationsOverview:
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
    custom = await _list_custom(session, ctx, settings)
    return IntegrationsOverview(provider_types=types, providers=cards, custom=custom)


async def _list_custom(session: AsyncSession, ctx: AuthContext, settings: Settings) -> list[IntegrationOut]:
    svc = IntegrationService(session, ctx, settings)
    rows = await svc.list_all()
    used = await svc.used_by([r.id for r in rows])
    slugs = await svc.tool_slugs(rows)
    return [
        integration_out(r, tool_slug=slugs.get(r.tool_id) if r.tool_id else None, used_by=used.get(r.id, []))
        for r in rows
    ]


async def _one(
    session: AsyncSession, ctx: AuthContext, settings: Settings, integration_id: uuid.UUID
) -> IntegrationOut:
    svc = IntegrationService(session, ctx, settings)
    row = await svc.get(integration_id)
    used = await svc.used_by([row.id])
    slugs = await svc.tool_slugs([row])
    return integration_out(
        row, tool_slug=slugs.get(row.tool_id) if row.tool_id else None, used_by=used.get(row.id, [])
    )


# ----------------------------------------------------------------------------- custom REST APIs (spec §7–§10)
@router.get("", response_model=list[IntegrationOut])
async def list_integrations(ctx: AdminAuth, session: DB, settings: Config) -> list[IntegrationOut]:
    return await _list_custom(session, ctx, settings)


@router.post("", response_model=IntegrationOut, status_code=status.HTTP_201_CREATED)
async def create_integration(
    body: IntegrationCreate, ctx: AdminAuth, session: DB, settings: Config, adapters: AdaptersDep
) -> IntegrationOut:
    row = await IntegrationService(session, ctx, settings).create(body, adapters.secrets)
    return await _one(session, ctx, settings, row.id)


@router.post("/parse-curl", response_model=CurlPreview)
async def parse_curl_preview(body: CurlParseIn, ctx: AdminAuth) -> CurlPreview:
    """Dry run: nothing is stored; detected secret values are returned only as masked previews."""
    return IntegrationService.preview_curl(body.curl)


@router.post("/import-curl", response_model=IntegrationOut, status_code=status.HTTP_201_CREATED)
async def import_curl(
    body: CurlImportIn, ctx: AdminAuth, session: DB, settings: Config, adapters: AdaptersDep
) -> IntegrationOut:
    """Spec §8: credentials in the cURL move into encrypted secret storage; the raw command is not kept."""
    row = await IntegrationService(session, ctx, settings).import_curl(
        name=body.name,
        description=body.description,
        curl=body.curl,
        create_tool=body.create_tool,
        secrets=adapters.secrets,
    )
    return await _one(session, ctx, settings, row.id)


@router.get("/{integration_id}", response_model=IntegrationOut)
async def get_integration(
    integration_id: uuid.UUID, ctx: AdminAuth, session: DB, settings: Config
) -> IntegrationOut:
    return await _one(session, ctx, settings, integration_id)


@router.patch("/{integration_id}", response_model=IntegrationOut)
async def update_integration(
    integration_id: uuid.UUID, body: IntegrationUpdate, ctx: AdminAuth, session: DB, settings: Config
) -> IntegrationOut:
    await IntegrationService(session, ctx, settings).update(integration_id, body)
    return await _one(session, ctx, settings, integration_id)


@router.delete("/{integration_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_integration(
    integration_id: uuid.UUID, ctx: AdminAuth, session: DB, settings: Config, adapters: AdaptersDep
) -> None:
    await IntegrationService(session, ctx, settings).delete(integration_id, adapters.secrets)


@router.post("/{integration_id}/secrets", response_model=IntegrationOut)
async def set_integration_secret(
    integration_id: uuid.UUID,
    body: IntegrationSecretIn,
    ctx: AdminAuth,
    session: DB,
    settings: Config,
    adapters: AdaptersDep,
) -> IntegrationOut:
    await IntegrationService(session, ctx, settings).set_secret(integration_id, body, adapters.secrets)
    return await _one(session, ctx, settings, integration_id)


@router.delete("/{integration_id}/secrets/{name}", response_model=IntegrationOut)
async def delete_integration_secret(
    integration_id: uuid.UUID, name: str, ctx: AdminAuth, session: DB, settings: Config, adapters: AdaptersDep
) -> IntegrationOut:
    await IntegrationService(session, ctx, settings).delete_secret(integration_id, name, adapters.secrets)
    return await _one(session, ctx, settings, integration_id)


@router.post("/{integration_id}/test", response_model=IntegrationTestOut)
async def test_integration(
    integration_id: uuid.UUID,
    body: IntegrationTestIn,
    ctx: AdminAuth,
    session: DB,
    settings: Config,
    adapters: AdaptersDep,
    request: Request,
) -> IntegrationTestOut:
    """Spec §9: Request → API → Response with status, latency, size and a redacted preview."""
    return await IntegrationService(session, ctx, settings).test(
        integration_id,
        body.variables,
        adapters.secrets,
        request.app.state.session_factory,
        transport=getattr(adapters, "http_transport", None),
    )
