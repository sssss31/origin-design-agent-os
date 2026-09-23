from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.v1.admin import AdminAuth
from app.core.authz import DB
from app.core.deps import AdaptersDep
from app.schemas.admin import (
    AgentCreate,
    AgentCurlImportIn,
    AgentImportOut,
    AgentOut,
    AgentSummaryOut,
    AgentTestOut,
    AgentTestRequest,
    AgentUpdate,
    AgentVersionInput,
    HandoffIn,
    PublishRequest,
    SkillBindingIn,
    SkillOrderIn,
    ToolBindingIn,
)
from app.services.admin_serializers import agent_out, agent_summary_out, provider_out
from app.services.agents import AgentService, import_agent_from_curl

router = APIRouter(prefix="/agents")


@router.get("", response_model=list[AgentSummaryOut])
async def list_agents(ctx: AdminAuth, session: DB) -> list[AgentSummaryOut]:
    return [agent_summary_out(a) for a in await AgentService(session, ctx).list()]


@router.post("", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
async def create_agent(body: AgentCreate, ctx: AdminAuth, session: DB) -> AgentOut:
    return await agent_out(session, await AgentService(session, ctx).create(body))


@router.post("/import-curl", response_model=AgentImportOut, status_code=status.HTTP_201_CREATED)
async def import_agent_curl(
    body: AgentCurlImportIn, ctx: AdminAuth, session: DB, adapters: AdaptersDep
) -> AgentImportOut:
    """Paste the agent's OpenAI cURL: provider key + model are configured and the agent is created."""
    from app.api.v1.admin.providers import _curl_preview
    from app.services.providers import ProviderService

    agent, provider, detected, published = await import_agent_from_curl(session, ctx, body, adapters)
    svc = ProviderService(session, ctx)
    connection = None
    if provider.secret_ref_id is not None:
        result = await svc.test(provider.id, adapters.secrets)
        from app.schemas.admin import ProviderConnectionOut

        connection = ProviderConnectionOut(
            success=result.ok,
            provider=provider.type,
            status="connected" if result.ok else "failed",
            message=result.message,
            latency_ms=result.latency_ms,
            available_models=result.available_models,
            tested_at=result.tested_at,
        )
    return AgentImportOut(
        agent=await agent_out(session, agent),
        provider=provider_out(await svc.get(provider.id), is_default=await svc.is_default(provider.id)),
        detected=_curl_preview(detected),
        published=published,
        connection=connection,
    )


@router.get("/{agent_id}", response_model=AgentOut)
async def get_agent(agent_id: uuid.UUID, ctx: AdminAuth, session: DB) -> AgentOut:
    return await agent_out(session, await AgentService(session, ctx).get(agent_id))


@router.patch("/{agent_id}", response_model=AgentOut)
async def update_agent(agent_id: uuid.UUID, body: AgentUpdate, ctx: AdminAuth, session: DB) -> AgentOut:
    return await agent_out(session, await AgentService(session, ctx).update(agent_id, body))


@router.post("/{agent_id}/versions", response_model=AgentOut)
async def save_agent_draft(
    agent_id: uuid.UUID, body: AgentVersionInput, ctx: AdminAuth, session: DB
) -> AgentOut:
    """Create or update the draft version. The active version is never mutated in place."""
    return await agent_out(session, await AgentService(session, ctx).save_draft(agent_id, body))


@router.post("/{agent_id}/publish", response_model=AgentOut)
async def publish_agent(agent_id: uuid.UUID, body: PublishRequest, ctx: AdminAuth, session: DB) -> AgentOut:
    """Publish the draft (validation gate) or roll back to a published `version_id`."""
    return await agent_out(session, await AgentService(session, ctx).publish(agent_id, body))


@router.post("/{agent_id}/test", response_model=AgentTestOut)
async def test_agent(
    agent_id: uuid.UUID, body: AgentTestRequest, ctx: AdminAuth, session: DB, adapters: AdaptersDep
) -> AgentTestOut:
    return await AgentService(session, ctx).test(agent_id, body, adapters)


@router.post("/{agent_id}/skills/{skill_id}", response_model=AgentOut)
async def attach_skill(
    agent_id: uuid.UUID, skill_id: uuid.UUID, ctx: AdminAuth, session: DB, body: SkillBindingIn | None = None
) -> AgentOut:
    return await agent_out(
        session, await AgentService(session, ctx).attach_skill(agent_id, skill_id, body or SkillBindingIn())
    )


@router.put("/{agent_id}/skills/order", response_model=AgentOut)
async def reorder_skills(agent_id: uuid.UUID, body: SkillOrderIn, ctx: AdminAuth, session: DB) -> AgentOut:
    return await agent_out(session, await AgentService(session, ctx).reorder_skills(agent_id, body.skill_ids))


@router.delete("/{agent_id}/skills/{skill_id}", response_model=AgentOut)
async def detach_skill(agent_id: uuid.UUID, skill_id: uuid.UUID, ctx: AdminAuth, session: DB) -> AgentOut:
    return await agent_out(session, await AgentService(session, ctx).detach_skill(agent_id, skill_id))


@router.post("/{agent_id}/tools/{tool_id}", response_model=AgentOut)
async def attach_tool(
    agent_id: uuid.UUID, tool_id: uuid.UUID, ctx: AdminAuth, session: DB, body: ToolBindingIn | None = None
) -> AgentOut:
    return await agent_out(
        session, await AgentService(session, ctx).attach_tool(agent_id, tool_id, body or ToolBindingIn())
    )


@router.delete("/{agent_id}/tools/{tool_id}", response_model=AgentOut)
async def detach_tool(agent_id: uuid.UUID, tool_id: uuid.UUID, ctx: AdminAuth, session: DB) -> AgentOut:
    return await agent_out(session, await AgentService(session, ctx).detach_tool(agent_id, tool_id))


@router.post("/{agent_id}/handoffs/{target_agent_id}", response_model=AgentOut)
async def add_handoff(
    agent_id: uuid.UUID,
    target_agent_id: uuid.UUID,
    ctx: AdminAuth,
    session: DB,
    body: HandoffIn | None = None,
) -> AgentOut:
    return await agent_out(
        session, await AgentService(session, ctx).add_handoff(agent_id, target_agent_id, body or HandoffIn())
    )


@router.delete("/{agent_id}/handoffs/{target_agent_id}", response_model=AgentOut)
async def remove_handoff(
    agent_id: uuid.UUID, target_agent_id: uuid.UUID, ctx: AdminAuth, session: DB
) -> AgentOut:
    return await agent_out(
        session, await AgentService(session, ctx).remove_handoff(agent_id, target_agent_id)
    )
