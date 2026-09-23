"""Agents: draft/publish/rollback, bindings, handoffs, sandbox test (spec §4, §12, §16 P2)."""

from __future__ import annotations

import time
import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.adapters.registry import Adapters
from app.core.authz import AuthContext
from app.core.errors import Conflict, NotFound, RateLimited, ValidationFailed
from app.db.base import utcnow
from app.domain.slugs import slugify
from app.models.agents import Agent, AgentHandoff, AgentSkillBinding, AgentToolBinding, AgentVersion
from app.models.identity import Organization
from app.models.providers import AIProvider
from app.models.skills import Skill
from app.models.tools import Tool
from app.models.workspace import Project, Workspace
from app.ports.runner import RunInput
from app.providers.base import ProviderError
from app.schemas.admin import (
    AgentCreate,
    AgentTestOut,
    AgentTestRequest,
    AgentUpdate,
    AgentVersionInput,
    HandoffIn,
    PublishRequest,
    SkillBindingIn,
    TestStep,
    TestUsage,
    ToolBindingIn,
)
from app.services import audit
from app.services.agent_factory import build_runtime_agent
from app.services.composer import ComposedSkill
from app.services.providers import provider_adapters
from app.services.usage import UsageContext, enforce_provider_limits, record_usage

VERSION_FIELDS = (
    "provider_id",
    "model",
    "instructions",
    "handoff_description",
    "model_settings",
    "input_schema",
    "output_schema",
    "can_ask_clarification",
    "max_steps",
    "timeout_seconds",
)


def _load_options() -> list[Any]:
    return [
        selectinload(Agent.versions).selectinload(AgentVersion.skill_bindings),
        selectinload(Agent.versions).selectinload(AgentVersion.tool_bindings),
        selectinload(Agent.versions).selectinload(AgentVersion.handoffs),
    ]


class AgentService:
    def __init__(self, session: AsyncSession, ctx: AuthContext) -> None:
        self.session = session
        self.ctx = ctx
        self.org_id = ctx.require_organization()

    # ------------------------------------------------------------------ helpers
    async def _audit(
        self, action: str, entity_id: uuid.UUID, before: dict | None = None, after: dict | None = None
    ) -> None:
        await audit.record(
            self.session,
            action=action,
            entity_type="agent",
            entity_id=entity_id,
            organization_id=self.org_id,
            actor_user_id=self.ctx.user_id,
            before=before,
            after=after,
            request_id=self.ctx.request_id,
            ip_address=self.ctx.ip_address,
        )

    def _query(self) -> Select[tuple[Agent]]:
        return select(Agent).options(*_load_options()).where(Agent.organization_id == self.org_id)

    async def list(self) -> list[Agent]:
        return list((await self.session.scalars(self._query().order_by(Agent.command))).all())

    async def get(self, agent_id: uuid.UUID) -> Agent:
        row = await self.session.scalar(
            self._query().where(Agent.id == agent_id).execution_options(populate_existing=True)
        )
        if row is None:
            raise NotFound("Agent not found", code="agent_not_found")
        return row

    @staticmethod
    def draft_of(agent: Agent) -> AgentVersion | None:
        return next((v for v in agent.versions if v.published_at is None), None)

    @staticmethod
    def active_of(agent: Agent) -> AgentVersion | None:
        return next((v for v in agent.versions if v.id == agent.active_version_id), None)

    async def _reload(self, agent: Agent) -> Agent:
        self.session.expire(agent, ["versions"])
        return await self.get(agent.id)

    @staticmethod
    def _apply(version: AgentVersion, data: AgentVersionInput) -> None:
        for k, v in data.model_dump(exclude_unset=True).items():
            if k == "change_note":
                if v is not None:
                    version.change_note = v
            elif v is not None or k in ("provider_id", "model"):
                setattr(version, k, v)

    async def _ensure_draft(self, agent: Agent) -> AgentVersion:
        draft = self.draft_of(agent)
        if draft is not None:
            return draft
        active = self.active_of(agent)
        draft = AgentVersion(
            agent_id=agent.id,
            version=max((v.version for v in agent.versions), default=0) + 1,
            created_by=self.ctx.user_id,
        )
        if active is not None:
            for k in VERSION_FIELDS:
                value = getattr(active, k)
                setattr(draft, k, dict(value) if isinstance(value, dict) else value)
        self.session.add(draft)
        await self.session.flush()
        if active is not None:
            for sb in active.skill_bindings:
                self.session.add(
                    AgentSkillBinding(
                        agent_version_id=draft.id,
                        skill_id=sb.skill_id,
                        skill_version_id=sb.skill_version_id,
                        priority=sb.priority,
                        enabled=sb.enabled,
                        variables=dict(sb.variables),
                    )
                )
            for tb in active.tool_bindings:
                self.session.add(
                    AgentToolBinding(
                        agent_version_id=draft.id,
                        tool_id=tb.tool_id,
                        enabled=tb.enabled,
                        settings_json=dict(tb.settings_json),
                        max_calls_per_run=tb.max_calls_per_run,
                    )
                )
            for h in active.handoffs:
                self.session.add(
                    AgentHandoff(
                        agent_version_id=draft.id,
                        target_agent_id=h.target_agent_id,
                        routing_hint=h.routing_hint,
                        is_failure_route=h.is_failure_route,
                    )
                )
            await self.session.flush()
        agent = await self._reload(agent)
        return next(v for v in agent.versions if v.id == draft.id)

    async def _check_command_free(self, agent: Agent, command: str) -> None:
        clash = await self.session.scalar(
            select(Agent.id).where(
                Agent.organization_id == self.org_id,
                Agent.command == command,
                Agent.status == "active",
                Agent.id != agent.id,
            )
        )
        if clash:
            raise Conflict(f"Another active agent already uses {command}", code="command_taken")

    # ------------------------------------------------------------------ CRUD
    async def create(self, data: AgentCreate) -> Agent:
        slug = data.slug or slugify(data.name)
        if await self.session.scalar(
            select(Agent.id).where(Agent.organization_id == self.org_id, Agent.slug == slug)
        ):
            raise Conflict(f"Agent slug '{slug}' already exists", code="slug_taken")
        agent = Agent(
            organization_id=self.org_id,
            name=data.name,
            slug=slug,
            command=data.command,
            description=data.description,
            is_manager=data.is_manager,
            status="draft",
            created_by=self.ctx.user_id,
            updated_by=self.ctx.user_id,
        )
        self.session.add(agent)
        await self.session.flush()
        version = AgentVersion(agent_id=agent.id, version=1, created_by=self.ctx.user_id)
        self._apply(version, data.version)
        self.session.add(version)
        await self.session.flush()
        await self._audit(
            "agent.created", agent.id, after={"name": agent.name, "slug": slug, "command": agent.command}
        )
        return await self.get(agent.id)

    async def update(self, agent_id: uuid.UUID, data: AgentUpdate) -> Agent:
        agent = await self.get(agent_id)
        before = {
            "name": agent.name,
            "command": agent.command,
            "description": agent.description,
            "status": agent.status,
            "is_manager": agent.is_manager,
        }
        changes = data.model_dump(exclude_unset=True)
        if "command" in changes and changes["command"] and agent.status == "active":
            await self._check_command_free(agent, changes["command"])
        if changes.get("status") == "active":
            if agent.active_version_id is None:
                raise ValidationFailed(
                    "Publish a version before activating the agent", code="no_published_version"
                )
            await self._check_command_free(agent, changes.get("command") or agent.command)
        for k, v in changes.items():
            if v is not None:
                setattr(agent, k, v)
        agent.updated_by = self.ctx.user_id
        await self.session.flush()
        action = {"disabled": "agent.disabled", "active": "agent.enabled"}.get(
            changes.get("status") or "", "agent.updated"
        )
        await self._audit(
            action,
            agent.id,
            before=before,
            after={
                "name": agent.name,
                "command": agent.command,
                "description": agent.description,
                "status": agent.status,
                "is_manager": agent.is_manager,
            },
        )
        return await self.get(agent.id)

    async def save_draft(self, agent_id: uuid.UUID, data: AgentVersionInput) -> Agent:
        agent = await self.get(agent_id)
        draft = await self._ensure_draft(agent)
        if data.provider_id is not None:
            provider = await self.session.get(AIProvider, data.provider_id)
            if provider is None or provider.organization_id != self.org_id:
                raise NotFound("Provider not found", code="provider_not_found")
        self._apply(draft, data)
        agent.updated_by = self.ctx.user_id
        await self.session.flush()
        await self._audit(
            "agent.draft_saved",
            agent.id,
            after={
                "version": draft.version,
                **{
                    k: v
                    for k, v in data.model_dump(exclude_unset=True, exclude_none=True).items()
                    if k != "instructions"
                },
                "instructions_chars": len(draft.instructions),
            },
        )
        return await self.get(agent.id)

    # ------------------------------------------------------------------ publish / rollback
    async def _validate(self, agent: Agent, version: AgentVersion) -> None:
        problems: list[str] = []
        if not version.instructions.strip():
            problems.append("instructions must not be empty")
        if version.provider_id is None:
            problems.append("provider is required")
        else:
            provider = await self.session.scalar(
                select(AIProvider)
                .options(selectinload(AIProvider.models))
                .where(AIProvider.id == version.provider_id, AIProvider.organization_id == self.org_id)
            )
            if provider is None:
                problems.append("provider not found in this organization")
            else:
                if not provider.enabled:
                    problems.append(f"provider '{provider.name}' is disabled")
                if not version.model:
                    problems.append("model is required")
                else:
                    allowed = {m.model for m in provider.models if m.enabled}
                    if allowed and version.model not in allowed:
                        problems.append(
                            f"model '{version.model}' is not in the provider allowlist {sorted(allowed)}"
                        )
                    overrides = next(
                        (m.capabilities for m in provider.models if m.model == version.model), None
                    )
                    adapter = provider_adapters().get(provider.type)
                    if adapter is not None:
                        caps = adapter.model_capabilities(version.model, overrides)
                        if caps.supports_image_generation and not caps.supports_tools:
                            problems.append(
                                f"model '{version.model}' is an image model; agents need a chat/reasoning "
                                "model (image models are used through the image.generate tool)"
                            )
                        if "temperature" in version.model_settings and not caps.supports_temperature:
                            problems.append(f"model '{version.model}' does not accept temperature; remove it")
                        if "reasoning_effort" in version.model_settings and not caps.supports_reasoning:
                            problems.append(f"model '{version.model}' does not accept reasoning settings")
        try:
            await self._check_command_free(agent, agent.command)
        except Conflict as exc:
            problems.append(exc.message)
        skill_ids = [b.skill_id for b in version.skill_bindings if b.enabled]
        if skill_ids:
            skills = (await self.session.scalars(select(Skill).where(Skill.id.in_(skill_ids)))).all()
            found = {s.id: s for s in skills}
            for b in version.skill_bindings:
                if not b.enabled:
                    continue
                s = found.get(b.skill_id)
                if s is None or s.organization_id != self.org_id:
                    problems.append(f"skill binding {b.skill_id} not found")
                elif s.status != "active" or (b.skill_version_id is None and s.active_version_id is None):
                    problems.append(f"skill '{s.slug}' must be active with a published version")
        tool_ids = [b.tool_id for b in version.tool_bindings if b.enabled]
        if tool_ids:
            tools = (await self.session.scalars(select(Tool).where(Tool.id.in_(tool_ids)))).all()
            found_t = {t.id: t for t in tools}
            for tb in version.tool_bindings:
                if not tb.enabled:
                    continue
                t = found_t.get(tb.tool_id)
                if t is None or t.organization_id != self.org_id:
                    problems.append(f"tool binding {tb.tool_id} not found")
                elif t.status != "active" or t.active_version_id is None:
                    problems.append(f"tool '{t.slug}' is disabled")
        if version.handoffs:
            targets = (
                await self.session.scalars(
                    select(Agent.id).where(
                        Agent.organization_id == self.org_id,
                        Agent.id.in_([h.target_agent_id for h in version.handoffs]),
                    )
                )
            ).all()
            for h in version.handoffs:
                if h.target_agent_id not in set(targets):
                    problems.append(f"handoff target {h.target_agent_id} not found")
        if problems:
            raise ValidationFailed(
                "Agent cannot be published", code="publish_validation_failed", details=problems
            )

    async def publish(self, agent_id: uuid.UUID, data: PublishRequest) -> Agent:
        agent = await self.get(agent_id)
        before = {"active_version_id": str(agent.active_version_id), "status": agent.status}
        if data.version_id is not None:
            target = next((v for v in agent.versions if v.id == data.version_id), None)
            if target is None or target.published_at is None:
                raise ValidationFailed(
                    "version_id must reference a published version of this agent", code="invalid_version"
                )
            await self._validate(agent, target)
            action = "agent.rolled_back"
        else:
            target = self.draft_of(agent)
            if target is None:
                raise ValidationFailed("Nothing to publish: no draft version", code="no_draft")
            await self._validate(agent, target)
            target.published_at = utcnow()
            if data.change_note:
                target.change_note = data.change_note
            action = "agent.published"
        agent.active_version_id = target.id
        agent.status = "active"
        agent.updated_by = self.ctx.user_id
        await self.session.flush()
        await self._audit(
            action,
            agent.id,
            before=before,
            after={"active_version_id": str(target.id), "version": target.version, "status": "active"},
        )
        return await self.get(agent.id)

    # ------------------------------------------------------------------ bindings (operate on the draft)
    async def attach_skill(self, agent_id: uuid.UUID, skill_id: uuid.UUID, data: SkillBindingIn) -> Agent:
        agent = await self.get(agent_id)
        skill = await self.session.scalar(
            select(Skill)
            .options(selectinload(Skill.versions))
            .where(Skill.id == skill_id, Skill.organization_id == self.org_id)
        )
        if skill is None:
            raise NotFound("Skill not found", code="skill_not_found")
        if data.skill_version_id is not None and not any(
            v.id == data.skill_version_id and v.published_at for v in skill.versions
        ):
            raise ValidationFailed(
                "skill_version_id must be a published version of this skill", code="invalid_skill_version"
            )
        draft = await self._ensure_draft(agent)
        existing = next((b for b in draft.skill_bindings if b.skill_id == skill_id), None)
        active_sv = next((v for v in skill.versions if v.id == skill.active_version_id), None)
        priority = (
            data.priority if data.priority is not None else (active_sv.default_priority if active_sv else 100)
        )
        if existing is None:
            self.session.add(
                AgentSkillBinding(
                    agent_version_id=draft.id,
                    skill_id=skill_id,
                    skill_version_id=data.skill_version_id,
                    priority=priority,
                    enabled=data.enabled,
                    variables=data.variables,
                )
            )
        else:
            existing.skill_version_id, existing.priority, existing.enabled, existing.variables = (
                data.skill_version_id,
                priority,
                data.enabled,
                data.variables,
            )
        await self.session.flush()
        await self._audit(
            "agent.skill_attached",
            agent.id,
            after={
                "version": draft.version,
                "skill": skill.slug,
                "priority": priority,
                "pinned": str(data.skill_version_id) if data.skill_version_id else None,
            },
        )
        return await self._reload(agent)

    async def reorder_skills(self, agent_id: uuid.UUID, skill_ids: Sequence[uuid.UUID]) -> Agent:
        agent = await self.get(agent_id)
        draft = await self._ensure_draft(agent)
        by_skill = {b.skill_id: b for b in draft.skill_bindings}
        unknown = [str(s) for s in skill_ids if s not in by_skill]
        if unknown:
            raise ValidationFailed(
                "skill_ids must all be attached to the draft", code="binding_not_found", details=unknown
            )
        for i, sid in enumerate(skill_ids):
            by_skill[sid].priority = (i + 1) * 10
        rest = [
            b
            for b in sorted(draft.skill_bindings, key=lambda b: b.priority)
            if b.skill_id not in set(skill_ids)
        ]
        for j, b in enumerate(rest):
            b.priority = (len(skill_ids) + j + 1) * 10
        await self.session.flush()
        await self._audit(
            "agent.skills_reordered",
            agent.id,
            after={"version": draft.version, "order": [str(s) for s in skill_ids]},
        )
        return await self._reload(agent)

    async def detach_skill(self, agent_id: uuid.UUID, skill_id: uuid.UUID) -> Agent:
        agent = await self.get(agent_id)
        draft = await self._ensure_draft(agent)
        binding = next((b for b in draft.skill_bindings if b.skill_id == skill_id), None)
        if binding is None:
            raise NotFound("Skill is not attached to the draft", code="binding_not_found")
        await self.session.delete(binding)
        await self.session.flush()
        await self._audit(
            "agent.skill_detached", agent.id, after={"version": draft.version, "skill_id": str(skill_id)}
        )
        return await self._reload(agent)

    async def attach_tool(self, agent_id: uuid.UUID, tool_id: uuid.UUID, data: ToolBindingIn) -> Agent:
        agent = await self.get(agent_id)
        tool = await self.session.scalar(
            select(Tool).where(Tool.id == tool_id, Tool.organization_id == self.org_id)
        )
        if tool is None:
            raise NotFound("Tool not found", code="tool_not_found")
        draft = await self._ensure_draft(agent)
        existing = next((b for b in draft.tool_bindings if b.tool_id == tool_id), None)
        if existing is None:
            self.session.add(
                AgentToolBinding(
                    agent_version_id=draft.id,
                    tool_id=tool_id,
                    enabled=data.enabled,
                    settings_json=data.settings_json,
                    max_calls_per_run=data.max_calls_per_run,
                )
            )
        else:
            existing.enabled, existing.settings_json, existing.max_calls_per_run = (
                data.enabled,
                data.settings_json,
                data.max_calls_per_run,
            )
        await self.session.flush()
        await self._audit(
            "agent.tool_attached",
            agent.id,
            after={"version": draft.version, "tool": tool.slug, "enabled": data.enabled},
        )
        return await self._reload(agent)

    async def detach_tool(self, agent_id: uuid.UUID, tool_id: uuid.UUID) -> Agent:
        agent = await self.get(agent_id)
        draft = await self._ensure_draft(agent)
        binding = next((b for b in draft.tool_bindings if b.tool_id == tool_id), None)
        if binding is None:
            raise NotFound("Tool is not attached to the draft", code="binding_not_found")
        await self.session.delete(binding)
        await self.session.flush()
        await self._audit(
            "agent.tool_detached", agent.id, after={"version": draft.version, "tool_id": str(tool_id)}
        )
        return await self._reload(agent)

    async def add_handoff(self, agent_id: uuid.UUID, target_agent_id: uuid.UUID, data: HandoffIn) -> Agent:
        agent = await self.get(agent_id)
        if target_agent_id == agent.id:
            raise ValidationFailed("An agent cannot hand off to itself", code="self_handoff")
        target = await self.session.scalar(
            select(Agent).where(Agent.id == target_agent_id, Agent.organization_id == self.org_id)
        )
        if target is None:
            raise NotFound("Target agent not found", code="agent_not_found")
        draft = await self._ensure_draft(agent)
        existing = next((h for h in draft.handoffs if h.target_agent_id == target_agent_id), None)
        if existing is None:
            self.session.add(
                AgentHandoff(
                    agent_version_id=draft.id,
                    target_agent_id=target_agent_id,
                    routing_hint=data.routing_hint,
                    is_failure_route=data.is_failure_route,
                )
            )
        else:
            existing.routing_hint, existing.is_failure_route = data.routing_hint, data.is_failure_route
        await self.session.flush()
        await self._audit(
            "agent.handoff_set",
            agent.id,
            after={
                "version": draft.version,
                "target": target.slug,
                "is_failure_route": data.is_failure_route,
            },
        )
        return await self._reload(agent)

    async def remove_handoff(self, agent_id: uuid.UUID, target_agent_id: uuid.UUID) -> Agent:
        agent = await self.get(agent_id)
        draft = await self._ensure_draft(agent)
        handoff = next((h for h in draft.handoffs if h.target_agent_id == target_agent_id), None)
        if handoff is None:
            raise NotFound("Handoff not found on the draft", code="handoff_not_found")
        await self.session.delete(handoff)
        await self.session.flush()
        await self._audit(
            "agent.handoff_removed",
            agent.id,
            after={"version": draft.version, "target_agent_id": str(target_agent_id)},
        )
        return await self._reload(agent)

    # ------------------------------------------------------------------ sandbox test
    async def test(
        self,
        agent_id: uuid.UUID,
        data: AgentTestRequest,
        adapters: Adapters,
        *,
        extra_skills: Sequence[ComposedSkill] | None = None,
    ) -> AgentTestOut:
        """Spec §16 test console: every stage is reported as a step; failures return a sanitized result."""
        steps: list[TestStep] = []

        def done(label: str, detail: str | None = None) -> None:
            steps.append(TestStep(label=label, status="done", detail=detail))

        def failed(label: str, detail: str) -> None:
            steps.append(TestStep(label=label, status="failed", detail=detail))

        agent = await self.get(agent_id)
        version = (
            (self.draft_of(agent) if data.use_draft else None)
            or self.active_of(agent)
            or self.draft_of(agent)
        )
        if version is None:
            raise ValidationFailed("Agent has no version to test", code="no_version")
        done("Agent loaded", f"{agent.name} v{version.version}")
        organization = await self.session.get(Organization, self.org_id)
        assert organization is not None
        workspace: Workspace | None = None
        project: Project | None = None
        if data.project_id is not None:
            project = await self.session.get(Project, data.project_id)
            if project is not None:
                workspace = await self.session.get(Workspace, project.workspace_id)
                if workspace is None or workspace.organization_id != self.org_id:
                    project, workspace = None, None
        try:
            resolved = await build_runtime_agent(
                self.session,
                agent,
                version,
                organization=organization,
                workspace=workspace,
                project=project,
                extra_skills=extra_skills,
            )
        except ValidationFailed as exc:
            failed("Provider loaded", exc.message)
            return self._test_failed(steps, agent, version, exc.code, exc.message)
        done("Provider loaded", f"{resolved.provider.name} · {resolved.runtime.model}")
        done(
            "Skills loaded",
            ", ".join(s for s in resolved.composition.sections if s.startswith("skill:")) or "none",
        )
        done(
            "Workspace context loaded",
            ", ".join(
                s
                for s in resolved.composition.sections
                if s not in ("platform_rules", "agent_instructions") and not s.startswith("skill:")
            )
            or "no project selected",
        )
        provider_adapter = adapters.providers.get(resolved.provider.type)
        if provider_adapter is None:
            failed("Provider connected", f"no runtime for {resolved.provider.type}")
            return self._test_failed(
                steps, agent, version, "runner_unavailable", "No runtime for this provider type."
            )
        runner = provider_adapter.runner
        credentials: dict[str, str] = {}
        if resolved.provider.secret_ref_id:
            try:
                credentials["api_key"] = await adapters.secrets.reveal(str(resolved.provider.secret_ref_id))
            except LookupError:
                failed("Provider connected", "the stored credential cannot be read")
                return self._test_failed(
                    steps, agent, version, "provider_secret_unavailable", "Credential unreadable."
                )
        if resolved.provider.base_url:
            credentials["base_url"] = resolved.provider.base_url
        if resolved.provider.type != "echo" and not credentials.get("api_key"):
            failed("Provider connected", "no API key configured — add one under Admin → API Integrations")
            return self._test_failed(
                steps, agent, version, "provider_secret_unavailable", "Provider has no API key."
            )
        try:
            await enforce_provider_limits(self.session, resolved.provider)
        except RateLimited as exc:
            failed("Provider connected", exc.message)
            return self._test_failed(steps, agent, version, exc.code, exc.message)
        resolved.runtime.provider_credentials = credentials
        done("Provider connected", f"{resolved.provider.type} ready")

        async def invoke_tool(slug: str, args: dict[str, Any]) -> dict[str, Any]:
            # Sandbox test never executes real tools; it records the call.
            return {"ok": True, "sandbox": True, "tool": slug, "args": args}

        async def emit(event_type: str, payload: dict[str, Any]) -> None:
            if event_type == "provider.retry":
                steps.append(
                    TestStep(
                        label="Agent executing", status="running", detail=f"retry {payload.get('attempt')}"
                    )
                )

        usage_ctx = UsageContext(
            organization_id=self.org_id,
            provider_type=resolved.provider.type,
            provider_id=resolved.provider.id,
            model=resolved.runtime.model,
            agent_id=agent.id,
            agent_version_id=version.id,
            user_id=self.ctx.user_id,
            command=agent.command,
        )
        started = time.perf_counter()
        try:
            outcome = await provider_adapter.execute(
                resolved.runtime, RunInput(user_input=data.input), invoke_tool=invoke_tool, emit=emit
            )
        except ProviderError as exc:
            duration = int((time.perf_counter() - started) * 1000)
            await record_usage(
                self.session, usage_ctx, {}, duration_ms=duration, status="error", error_code=exc.code
            )
            failed("Agent executing", exc.message)
            return self._test_failed(
                steps, agent, version, exc.code, exc.message, resolved=resolved, duration=duration
            )
        duration = int((time.perf_counter() - started) * 1000)
        done("Agent executing", f"{outcome.steps} steps · {duration} ms")
        done(
            "Response received",
            "clarification requested"
            if outcome.requires_clarification
            else f"{len(outcome.output_text)} chars",
        )
        _, estimate = await record_usage(
            self.session, usage_ctx, outcome.usage, duration_ms=duration, status="test"
        )
        done(
            "Usage recorded",
            f"${estimate.estimated_cost_usd:.4f}"
            if estimate.priced
            else "no price configured for this model",
        )
        await self._audit(
            "agent.tested",
            agent.id,
            after={
                "version": version.version,
                "runner": runner.name,
                "steps": outcome.steps,
                "duration_ms": duration,
                "estimated_cost_usd": estimate.estimated_cost_usd,
            },
        )
        return AgentTestOut(
            steps=steps,
            usage=TestUsage(
                input_tokens=estimate.input_tokens,
                cached_input_tokens=estimate.cached_input_tokens,
                output_tokens=estimate.output_tokens,
                reasoning_tokens=estimate.reasoning_tokens,
                tool_calls=estimate.tool_calls,
                estimated_cost_usd=estimate.estimated_cost_usd,
                priced=estimate.priced,
                attempts=int(outcome.usage.get("attempts", 1) or 1),
            ),
            agent_slug=agent.slug,
            version=version.version,
            provider_type=resolved.provider.type,
            model=resolved.runtime.model,
            runner=runner.name,
            output_text=outcome.output_text,
            structured_output=outcome.structured_output,
            requires_clarification=outcome.requires_clarification,
            question=outcome.question,
            defaults_used=outcome.defaults_used,
            steps_count=outcome.steps,
            instruction_sections=resolved.composition.sections,
            instruction_chars=resolved.composition.chars,
            tools=[t.slug for t in resolved.runtime.tools],
            duration_ms=duration,
        )

    @staticmethod
    def _test_failed(
        steps: Sequence[TestStep],
        agent: Agent,
        version: AgentVersion,
        code: str,
        message: str,
        *,
        resolved: Any = None,
        duration: int = 0,
    ) -> AgentTestOut:
        return AgentTestOut(
            steps=list(steps),
            error_code=code,
            error_message=message,
            agent_slug=agent.slug,
            version=version.version,
            provider_type=resolved.provider.type if resolved else "",
            model=resolved.runtime.model if resolved else (version.model or ""),
            runner="",
            output_text="",
            structured_output=None,
            requires_clarification=False,
            question=None,
            defaults_used=[],
            steps_count=0,
            instruction_sections=resolved.composition.sections if resolved else [],
            instruction_chars=resolved.composition.chars if resolved else 0,
            tools=[t.slug for t in resolved.runtime.tools] if resolved else [],
            duration_ms=duration,
        )


async def list_commands(session: AsyncSession, organization_id: uuid.UUID) -> list[Agent]:
    """Active agents with their commands — for the composer autocomplete (any member)."""
    rows = await session.scalars(
        select(Agent)
        .where(
            Agent.organization_id == organization_id,
            Agent.status == "active",
            Agent.active_version_id.is_not(None),
        )
        .order_by(Agent.command)
    )
    return list(rows.all())
