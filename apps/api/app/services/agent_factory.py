"""Builds an immutable RuntimeAgent from a stored agent version (spec §12 AgentFactory).

Resolves: provider + model, skill versions (pinned or active) ordered by priority, tool
bindings → tool specs, and composes the final instructions. Used by the admin Test
endpoint now and by the run executor from Phase 4 onwards.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import ValidationFailed
from app.models.agents import Agent, AgentVersion
from app.models.identity import Organization
from app.models.providers import AIProvider
from app.models.skills import Skill, SkillVersion
from app.models.tools import Tool
from app.models.workspace import Project, ProjectRule, Workspace
from app.ports.runner import RuntimeAgent, RuntimeTool
from app.services.composer import ComposedSkill, Composition, CompositionInput, compose


@dataclass(slots=True)
class ResolvedAgent:
    runtime: RuntimeAgent
    composition: Composition
    provider: AIProvider
    tool_ids: dict[str, str]  # slug -> tool id


async def resolve_skills(session: AsyncSession, version: AgentVersion) -> list[ComposedSkill]:
    out: list[ComposedSkill] = []
    bindings = [b for b in version.skill_bindings if b.enabled]
    if not bindings:
        return out
    skills = {
        s.id: s
        for s in (
            await session.scalars(
                select(Skill)
                .options(selectinload(Skill.versions))
                .where(Skill.id.in_([b.skill_id for b in bindings]))
            )
        ).all()
    }
    for b in bindings:
        skill = skills.get(b.skill_id)
        if skill is None or skill.status != "active":
            continue
        sv: SkillVersion | None
        if b.skill_version_id:
            sv = next((v for v in skill.versions if v.id == b.skill_version_id and v.published_at), None)
        else:
            sv = next((v for v in skill.versions if v.id == skill.active_version_id), None)
        if sv is None:
            continue
        variables = {**sv.variables_defaults, **b.variables}
        out.append(
            ComposedSkill(
                name=skill.name,
                slug=skill.slug,
                version=sv.version,
                instructions=sv.instructions,
                priority=b.priority,
                variables=variables,
            )
        )
    return out


async def resolve_tools(
    session: AsyncSession, version: AgentVersion
) -> tuple[list[RuntimeTool], dict[str, str]]:
    bindings = [b for b in version.tool_bindings if b.enabled]
    if not bindings:
        return [], {}
    tools = (
        await session.scalars(
            select(Tool)
            .options(selectinload(Tool.versions))
            .where(Tool.id.in_([b.tool_id for b in bindings]))
        )
    ).all()
    runtime: list[RuntimeTool] = []
    ids: dict[str, str] = {}
    for tool in tools:
        if tool.status != "active":
            continue
        tv = next((v for v in tool.versions if v.id == tool.active_version_id), None)
        if tv is None:
            continue
        runtime.append(
            RuntimeTool(
                slug=tool.slug,
                display_name=tool.display_name,
                description=tool.description,
                input_schema=tv.input_schema,
                output_schema=tv.output_schema,
            )
        )
        ids[tool.slug] = str(tool.id)
    runtime.sort(key=lambda t: t.slug)
    return runtime, ids


async def build_runtime_agent(
    session: AsyncSession,
    agent: Agent,
    version: AgentVersion,
    *,
    organization: Organization,
    workspace: Workspace | None = None,
    project: Project | None = None,
    context_summary: str | None = None,
    user_request: str | None = None,
    extra_skills: Sequence[ComposedSkill] | None = None,
) -> ResolvedAgent:
    if version.provider_id is None or not version.model:
        raise ValidationFailed("Agent version has no provider/model configured", code="agent_not_configured")
    provider = await session.get(AIProvider, version.provider_id)
    if provider is None or provider.organization_id != agent.organization_id:
        raise ValidationFailed("Agent provider not found in this organization", code="provider_not_found")
    if not provider.enabled:
        raise ValidationFailed(f"Provider '{provider.name}' is disabled", code="provider_disabled")

    skills = await resolve_skills(session, version)
    if extra_skills:
        # a sandbox test replaces any attached copy of the same skill with the version under test
        replaced = {e.slug for e in extra_skills}
        skills = [s for s in skills if s.slug not in replaced] + list(extra_skills)
    tools, tool_ids = await resolve_tools(session, version)
    project_rules: list[str] = []
    if project is not None:
        rules = await session.scalars(
            select(ProjectRule)
            .where(ProjectRule.project_id == project.id, ProjectRule.is_active.is_(True))
            .order_by(ProjectRule.priority)
        )
        project_rules = [r.rule_text for r in rules.all()]
        if project.summary_text and not context_summary:
            context_summary = project.summary_text
    brand_summary = None
    if workspace is not None and workspace.brand_config:
        brand_summary = "\n".join(f"- {k}: {v}" for k, v in sorted(workspace.brand_config.items()))
    composition = compose(
        CompositionInput(
            agent_instructions=version.instructions,
            organization_rules=organization.global_rules,
            skills=skills,
            workspace_rules=workspace.rules_text if workspace else None,
            project_rules=project_rules,
            brand_summary=brand_summary,
            context_summary=context_summary,
            user_request=None,  # the user request is passed as run input, not baked into instructions
        )
    )
    runtime = RuntimeAgent(
        slug=agent.slug,
        name=agent.name,
        version=version.version,
        instructions=composition.text,
        model=version.model,
        provider_type=provider.type,
        model_settings=dict(version.model_settings),
        tools=tools,
        output_schema=version.output_schema or None,
        can_ask_clarification=version.can_ask_clarification,
        max_steps=version.max_steps,
        timeout_seconds=version.timeout_seconds,
    )
    _ = user_request
    return ResolvedAgent(runtime=runtime, composition=composition, provider=provider, tool_ids=tool_ids)
