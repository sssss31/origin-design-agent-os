"""Slash-command routing (spec §12 steps 1–3)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import ValidationFailed
from app.domain.slash import ParsedMessage, normalize_command
from app.models.agents import Agent, AgentVersion
from app.models.identity import Organization


@dataclass(slots=True)
class RouteDecision:
    agent: Agent
    version: AgentVersion
    explicit: bool
    command: str | None


async def _active_agent(
    session: AsyncSession,
    org_id: uuid.UUID,
    *,
    command: str | None = None,
    agent_id: uuid.UUID | None = None,
    manager: bool = False,
) -> Agent | None:
    q = (
        select(Agent)
        .options(selectinload(Agent.versions))
        .where(
            Agent.organization_id == org_id, Agent.status == "active", Agent.active_version_id.is_not(None)
        )
    )
    if command is not None:
        q = q.where(Agent.command == command)
    if agent_id is not None:
        q = q.where(Agent.id == agent_id)
    if manager:
        q = q.where(Agent.is_manager.is_(True)).order_by(Agent.created_at)
    return await session.scalar(q)


async def _default_agent(session: AsyncSession, org_id: uuid.UUID) -> Agent | None:
    org = await session.get(Organization, org_id)
    ref = (org.settings_json or {}).get("default_agent_id") if org else None
    if ref:
        try:
            agent = await _active_agent(session, org_id, agent_id=uuid.UUID(str(ref)))
        except ValueError:
            agent = None
        if agent is not None and not agent.is_manager:
            return agent
    q = (
        select(Agent)
        .options(selectinload(Agent.versions))
        .where(
            Agent.organization_id == org_id,
            Agent.status == "active",
            Agent.active_version_id.is_not(None),
            Agent.is_manager.is_(False),
            Agent.connection_type != "origin",
        )
        .order_by(Agent.command)
        .limit(1)
    )
    return await session.scalar(q)


async def resolve_route(
    session: AsyncSession,
    org_id: uuid.UUID,
    parsed: ParsedMessage,
    *,
    command_override: str | None = None,
    preferred_agent_id: uuid.UUID | None = None,
) -> RouteDecision:
    command = normalize_command(command_override) if command_override else parsed.command
    agent: Agent | None = None
    explicit = False
    if preferred_agent_id is not None:
        agent = await _active_agent(session, org_id, agent_id=preferred_agent_id)
        if agent is None:
            raise ValidationFailed("The requested agent is not active", code="agent_unavailable")
        explicit = True
        command = command or agent.command  # sticky/preferred routing is attributed to the agent's command
    elif command is not None and command != "/auto":
        agent = await _active_agent(session, org_id, command=command)
        if agent is None:
            # recoverable validation error (spec §14): the agent may have been disabled meanwhile
            raise ValidationFailed(
                f"No active agent handles {command}", code="agent_unavailable", details={"command": command}
            )
        explicit = True
    else:
        # Chatbot default: a plain message with no agent yet goes to the organisation's default
        # agent (Settings), else the first connected external agent, else the Manager.
        agent = await _default_agent(session, org_id)
        if agent is not None:
            command = agent.command
        else:
            agent = await _active_agent(session, org_id, manager=True)
        if agent is None:
            raise ValidationFailed(
                "No agent is connected yet; ask an admin to add one under Settings → Agents",
                code="no_manager",
            )
    version = next((v for v in agent.versions if v.id == agent.active_version_id), None)
    if version is None:
        raise ValidationFailed("Agent has no published version", code="agent_unavailable")
    return RouteDecision(agent=agent, version=version, explicit=explicit, command=command)
