from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.v1.admin import AdminAuth
from app.core.authz import DB
from app.core.deps import AdaptersDep
from app.schemas.admin import (
    AgentCreate,
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
from app.services.admin_serializers import agent_out, agent_summary_out
from app.services.agents import AgentService

router = APIRouter(prefix="/agents")


@router.get("", response_model=list[AgentSummaryOut])
async def list_agents(ctx: AdminAuth, session: DB) -> list[AgentSummaryOut]:
    return [agent_summary_out(a) for a in await AgentService(session, ctx).list()]


@router.post("", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
async def create_agent(body: AgentCreate, ctx: AdminAuth, session: DB) -> AgentOut:
    return await agent_out(session, await AgentService(session, ctx).create(body))


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
