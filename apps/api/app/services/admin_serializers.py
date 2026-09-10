"""ORM → response schemas for admin entities (bulk-resolves names for bindings)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agents import Agent, AgentVersion
from app.models.providers import AIProvider
from app.models.skills import Skill, SkillVersion
from app.models.tools import Tool, ToolVersion
from app.schemas.admin import (
    AgentOut,
    AgentSummaryOut,
    AgentVersionOut,
    CommandOut,
    HandoffOut,
    ProviderModelOut,
    ProviderOut,
    SkillBindingOut,
    SkillFileOut,
    SkillOut,
    SkillVersionOut,
    ToolBindingOut,
    ToolOut,
    ToolPermissionOut,
    ToolVersionOut,
)
from app.schemas.common import from_orm


def provider_out(p: AIProvider) -> ProviderOut:
    return from_orm(
        ProviderOut,
        p,
        has_secret=p.secret_ref_id is not None,
        models=[from_orm(ProviderModelOut, m) for m in p.models],
    )


def _tool_version_out(v: ToolVersion) -> ToolVersionOut:
    return from_orm(ToolVersionOut, v, has_secret=v.secret_ref_id is not None)


def tool_out(t: Tool) -> ToolOut:
    active = next((v for v in t.versions if v.id == t.active_version_id), None)
    return from_orm(
        ToolOut,
        t,
        active_version=_tool_version_out(active) if active else None,
        permissions=[from_orm(ToolPermissionOut, p) for p in t.permissions],
    )


def _skill_version_out(v: SkillVersion) -> SkillVersionOut:
    return from_orm(SkillVersionOut, v, files=[from_orm(SkillFileOut, f) for f in v.files])


def skill_out(s: Skill) -> SkillOut:
    versions = sorted(s.versions, key=lambda v: v.version)
    active = next((v for v in versions if v.id == s.active_version_id), None)
    draft = next((v for v in versions if v.published_at is None), None)
    return from_orm(
        SkillOut,
        s,
        active_version=_skill_version_out(active) if active else None,
        draft_version=_skill_version_out(draft) if draft else None,
        versions=[_skill_version_out(v) for v in versions],
    )


def agent_summary_out(a: Agent) -> AgentSummaryOut:
    active = next((v for v in a.versions if v.id == a.active_version_id), None)
    return from_orm(
        AgentSummaryOut,
        a,
        active_version_number=active.version if active else None,
        has_draft=any(v.published_at is None for v in a.versions),
        model=active.model if active else next((v.model for v in a.versions if v.published_at is None), None),
    )


async def agent_out(session: AsyncSession, a: Agent) -> AgentOut:
    skill_ids: set[uuid.UUID] = set()
    tool_ids: set[uuid.UUID] = set()
    target_ids: set[uuid.UUID] = set()
    for v in a.versions:
        skill_ids.update(b.skill_id for b in v.skill_bindings)
        tool_ids.update(b.tool_id for b in v.tool_bindings)
        target_ids.update(h.target_agent_id for h in v.handoffs)
    skills = (
        {s.id: s for s in (await session.scalars(select(Skill).where(Skill.id.in_(skill_ids)))).all()}
        if skill_ids
        else {}
    )
    tools = (
        {t.id: t for t in (await session.scalars(select(Tool).where(Tool.id.in_(tool_ids)))).all()}
        if tool_ids
        else {}
    )
    targets = (
        {t.id: t for t in (await session.scalars(select(Agent).where(Agent.id.in_(target_ids)))).all()}
        if target_ids
        else {}
    )

    def version_out(v: AgentVersion) -> AgentVersionOut:
        return from_orm(
            AgentVersionOut,
            v,
            skills=[
                from_orm(
                    SkillBindingOut,
                    b,
                    skill_name=getattr(skills.get(b.skill_id), "name", None),
                    skill_slug=getattr(skills.get(b.skill_id), "slug", None),
                )
                for b in sorted(v.skill_bindings, key=lambda b: b.priority)
            ],
            tools=[
                from_orm(
                    ToolBindingOut,
                    b,
                    tool_slug=getattr(tools.get(b.tool_id), "slug", None),
                    tool_display_name=getattr(tools.get(b.tool_id), "display_name", None),
                )
                for b in v.tool_bindings
            ],
            handoffs=[
                from_orm(
                    HandoffOut,
                    h,
                    target_agent_name=getattr(targets.get(h.target_agent_id), "name", None),
                    target_agent_command=getattr(targets.get(h.target_agent_id), "command", None),
                )
                for h in v.handoffs
            ],
        )

    versions = sorted(a.versions, key=lambda v: v.version)
    active = next((v for v in versions if v.id == a.active_version_id), None)
    draft = next((v for v in versions if v.published_at is None), None)
    summary = agent_summary_out(a)
    return AgentOut(
        **summary.model_dump(),
        active_version=version_out(active) if active else None,
        draft_version=version_out(draft) if draft else None,
        versions=[version_out(v) for v in versions],
    )


def command_out(a: Agent) -> CommandOut:
    return CommandOut(
        agent_id=a.id,
        name=a.name,
        slug=a.slug,
        command=a.command,
        description=a.description,
        is_manager=a.is_manager,
    )
