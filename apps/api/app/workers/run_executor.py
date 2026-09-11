"""RunExecutor: turns a queued WorkflowRun into events, node results, artifacts and a reply.

One worker owns a run at a time (SELECT … FOR UPDATE SKIP LOCKED). Every state change is
persisted together with its execution event and only then published, so a refresh, a
reconnect or a worker restart always reconstructs the same timeline (ADR 0003).
"""

from __future__ import annotations

import asyncio
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.adapters.registry import Adapters
from app.core.config import Settings
from app.core.logging import get_logger, redact
from app.domain.events import EventType, SafeEventPayload
from app.domain.qc import parse_report
from app.domain.roles import Role, has_at_least
from app.domain.run_state import NodeState, RunState
from app.models.agents import Agent, AgentVersion
from app.models.chat import Conversation
from app.models.files import Artifact, ArtifactVersion
from app.models.identity import Organization, OrganizationMember
from app.models.tools import Tool, ToolPermission
from app.models.workflows import ApiUsage, ErrorEvent, NodeRun, WorkflowRun
from app.models.workspace import Project, Workspace
from app.ports.queue import Job
from app.ports.runner import ProducedFile, RunInput, RunOutcome
from app.ports.tools import ToolCall, ToolSpec
from app.services.agent_factory import build_runtime_agent
from app.services.artifacts import ArtifactService
from app.services.context import build_context
from app.services.conversations import ConversationService
from app.services.events import EventRecorder
from app.services.runs import SAVE_NODE_INDEX
from app.tools import registry as tool_registry
from app.tools.context import ToolContext

log = get_logger("executor")


class NodeFailure(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


def _summary(text: str, limit: int = 500) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


class RunExecutor:
    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], adapters: Adapters, settings: Settings
    ) -> None:
        self.session_factory = session_factory
        self.adapters = adapters
        self.settings = settings
        tool_registry.load_builtins()

    async def handle(self, job: Job) -> None:
        await self.execute(uuid.UUID(str(job.payload["run_id"])))

    # ------------------------------------------------------------------ main loop
    async def execute(self, run_id: uuid.UUID) -> None:
        async with self.session_factory() as session:
            run = await session.scalar(
                select(WorkflowRun)
                .options(selectinload(WorkflowRun.nodes))
                .where(WorkflowRun.id == run_id, WorkflowRun.status == RunState.QUEUED)
                .with_for_update(skip_locked=True)
            )
            if run is None:
                log.info("run_not_claimable", run_id=str(run_id))
                return
            recorder = EventRecorder(session, self.adapters.events, run.id)
            now = datetime.now(UTC)
            run.status = RunState.RUNNING
            run.started_at = run.started_at or now
            run.heartbeat_at = now
            await recorder.add(
                EventType.RUN_STARTED, SafeEventPayload(run_status=run.status, agent_slug=None)
            )
            await recorder.commit()

            conversation = await session.get(Conversation, run.conversation_id)
            project = await session.get(Project, run.project_id)
            workspace = await session.get(Workspace, run.workspace_id)
            organization = await session.get(Organization, run.organization_id)
            assert conversation and project and workspace and organization
            creator_role = (
                await session.scalar(
                    select(OrganizationMember.role).where(
                        OrganizationMember.organization_id == run.organization_id,
                        OrganizationMember.user_id == run.created_by,
                    )
                )
                if run.created_by
                else None
            )

            while True:
                await session.refresh(run, attribute_names=["cancel_requested", "nodes"])
                if run.cancel_requested:
                    await self._cancel(session, recorder, run)
                    return
                node = next(
                    (
                        n
                        for n in sorted(run.nodes, key=lambda n: n.index)
                        if n.status == NodeState.PENDING
                        or (n.status == NodeState.WAITING_FOR_USER and n.answer is not None)
                    ),
                    None,
                )
                if node is None:
                    break
                try:
                    paused = await self._run_node(
                        session,
                        recorder,
                        run,
                        node,
                        conversation=conversation,
                        project=project,
                        workspace=workspace,
                        organization=organization,
                        creator_role=creator_role,
                    )
                except NodeFailure as failure:
                    await self._fail(session, recorder, run, node, failure)
                    return
                except TimeoutError:
                    await self._fail(
                        session,
                        recorder,
                        run,
                        node,
                        NodeFailure("timeout", "step exceeded its time limit", retryable=True),
                    )
                    return
                except Exception as exc:  # unexpected: keep the run durable and report safely
                    log.exception("node_crashed", run_id=str(run.id), node=node.node_id)
                    await self._fail(
                        session,
                        recorder,
                        run,
                        node,
                        NodeFailure(
                            "internal_error", redact(f"{type(exc).__name__}: {exc}")[:500], retryable=True
                        ),
                    )
                    return
                if paused:
                    return
            run.status = RunState.SUCCEEDED
            run.finished_at = datetime.now(UTC)
            await recorder.add(
                EventType.RUN_COMPLETED,
                SafeEventPayload(
                    run_status=run.status,
                    output_summary=_summary(str(run.result_json.get("output_text", ""))),
                ),
            )
            await recorder.commit()

    async def _cancel(self, session: AsyncSession, recorder: EventRecorder, run: WorkflowRun) -> None:
        for n in run.nodes:
            if n.status in (NodeState.PENDING, NodeState.WAITING_FOR_USER):
                n.status = NodeState.SKIPPED
        run.status = RunState.CANCELLED
        run.finished_at = datetime.now(UTC)
        await recorder.add(EventType.RUN_CANCELLED, SafeEventPayload(run_status=run.status))
        await recorder.commit()

    async def _fail(
        self,
        session: AsyncSession,
        recorder: EventRecorder,
        run: WorkflowRun,
        node: NodeRun,
        failure: NodeFailure,
    ) -> None:
        node.status = NodeState.FAILED
        node.finished_at = datetime.now(UTC)
        node.error_json = {"code": failure.code, "message": failure.message, "retryable": failure.retryable}
        run.status = RunState.FAILED
        run.finished_at = node.finished_at
        run.error_json = {**node.error_json, "node_id": node.node_id}
        session.add(
            ErrorEvent(
                organization_id=run.organization_id,
                run_id=run.id,
                node_run_id=node.id,
                code=failure.code,
                message=failure.message,
                retryable=failure.retryable,
            )
        )
        await recorder.add(
            EventType.NODE_FAILED,
            SafeEventPayload(
                node_id=node.node_id,
                node_name=node.name,
                node_index=node.index,
                node_status=node.status,
                error_code=failure.code,
                error_message=failure.message,
                retryable=failure.retryable,
            ),
            node_run_id=node.id,
        )
        await recorder.add(
            EventType.RUN_FAILED,
            SafeEventPayload(
                run_status=run.status,
                error_code=failure.code,
                error_message=failure.message,
                retryable=failure.retryable,
            ),
        )
        await recorder.commit()

    # ------------------------------------------------------------------ nodes
    async def _run_node(
        self,
        session: AsyncSession,
        recorder: EventRecorder,
        run: WorkflowRun,
        node: NodeRun,
        *,
        conversation: Conversation,
        project: Project,
        workspace: Workspace,
        organization: Organization,
        creator_role: str | None,
    ) -> bool:
        """Returns True when the run paused for the user."""
        started = datetime.now(UTC)
        node.status = NodeState.RUNNING
        node.started_at = node.started_at or started
        run.heartbeat_at = started
        await recorder.add(
            EventType.NODE_STARTED,
            SafeEventPayload(
                node_id=node.node_id, node_name=node.name, node_index=node.index, node_status=node.status
            ),
            node_run_id=node.id,
        )
        await recorder.commit()

        if node.kind == "parse":
            node.output_json = {
                "command": run.command,
                "body": run.input_json.get("body", ""),
                "explicit": run.input_json.get("explicit", False),
            }
        elif node.kind == "context":
            package = await build_context(
                session,
                project=project,
                workspace=workspace,
                conversation_id=run.conversation_id,
                user_request=run.user_input,
                exclude_message_id=run.message_id,
                selected_asset_ids=[uuid.UUID(a) for a in run.input_json.get("selected_asset_ids", [])],
                selected_artifact_ids=[uuid.UUID(a) for a in run.input_json.get("selected_artifact_ids", [])],
                embeddings=self.adapters.embeddings,
            )
            run.input_json = {
                **run.input_json,
                "context_summary": package.summary,
                "context_sources": package.sources,
                "attachments": package.attachments,
            }
            node.output_json = {
                "sources": package.sources,
                "attachments": len(package.attachments),
                "chars": len(package.summary),
            }
            await recorder.add(
                EventType.CONTEXT_LOADED,
                SafeEventPayload(node_id=node.node_id, context_sources=package.sources),
                node_run_id=node.id,
            )
        elif node.kind in ("agent", "manager"):
            paused = await self._run_agent_node(
                session,
                recorder,
                run,
                node,
                conversation=conversation,
                project=project,
                workspace=workspace,
                organization=organization,
                creator_role=creator_role,
            )
            if paused:
                return True
        elif node.kind == "save":
            await self._save_result(session, run, node, conversation)
        else:
            raise NodeFailure("unknown_node_kind", f"unsupported node kind {node.kind}")

        node.status = NodeState.SUCCEEDED
        node.finished_at = datetime.now(UTC)
        duration = int((node.finished_at - started).total_seconds() * 1000)
        payload = SafeEventPayload(
            node_id=node.node_id,
            node_name=node.name,
            node_index=node.index,
            node_status=node.status,
            duration_ms=duration,
            output_summary=_summary(str(node.output_json.get("output_text", ""))) or None,
        )
        if node.output_json.get("qc_passed") is not None:
            payload.qc_passed = bool(node.output_json["qc_passed"])
            payload.findings_count = int(node.output_json.get("findings_count", 0))
        await recorder.add(EventType.NODE_COMPLETED, payload, node_run_id=node.id)
        await recorder.commit()
        return False

    async def _run_agent_node(
        self,
        session: AsyncSession,
        recorder: EventRecorder,
        run: WorkflowRun,
        node: NodeRun,
        *,
        conversation: Conversation,
        project: Project,
        workspace: Workspace,
        organization: Organization,
        creator_role: str | None,
    ) -> bool:
        agent = await session.scalar(
            select(Agent).options(selectinload(Agent.versions)).where(Agent.id == node.agent_id)
        )
        if agent is None:
            raise NodeFailure("agent_missing", "the agent for this step no longer exists")
        version = next((v for v in agent.versions if v.id == node.agent_version_id), None) or next(
            (v for v in agent.versions if v.id == agent.active_version_id), None
        )
        if version is None:
            raise NodeFailure("agent_unpublished", f"agent {agent.slug} has no published version")
        node.agent_version_id = version.id
        version = await session.scalar(
            select(AgentVersion)
            .options(
                selectinload(AgentVersion.skill_bindings),
                selectinload(AgentVersion.tool_bindings),
                selectinload(AgentVersion.handoffs),
            )
            .where(AgentVersion.id == version.id)
        )
        assert version is not None

        context_summary = run.input_json.get("context_summary", "")
        if node.input_json.get("instruction"):
            context_summary = (
                f"{context_summary}\n\nManager instruction for this step: {node.input_json['instruction']}"
            )
        if node.input_json.get("qc_findings"):
            context_summary = f"{context_summary}\n\nQC findings to fix:\n" + "\n".join(
                f"- {f}" for f in node.input_json["qc_findings"]
            )
        try:
            resolved = await build_runtime_agent(
                session,
                agent,
                version,
                organization=organization,
                workspace=workspace,
                project=project,
                context_summary=context_summary,
            )
        except Exception as exc:
            raise NodeFailure("agent_not_configured", redact(str(exc))[:300]) from exc
        runtime = resolved.runtime
        runner = self.adapters.runners.get(resolved.provider.type)
        if runner is None:
            raise NodeFailure("runner_unavailable", f"no runtime for provider type {resolved.provider.type}")
        credentials: dict[str, str] = {}
        if resolved.provider.secret_ref_id:
            try:
                credentials["api_key"] = await self.adapters.secrets.reveal(
                    str(resolved.provider.secret_ref_id)
                )
            except LookupError as exc:
                raise NodeFailure(
                    "provider_secret_unavailable", "the provider credential cannot be read", retryable=False
                ) from exc
        if resolved.provider.base_url:
            credentials["base_url"] = resolved.provider.base_url
        runtime.provider_credentials = credentials
        await recorder.add(
            EventType.AGENT_STARTED,
            SafeEventPayload(
                node_id=node.node_id,
                agent_slug=agent.slug,
                agent_name=agent.name,
                agent_version=version.version,
                context_sources=run.input_json.get("context_sources"),
            ),
            node_run_id=node.id,
        )
        await recorder.commit()

        # ---- tool invoker: bindings + permissions + limits + events + artifacts
        bound_tools = {t.slug: t for t in runtime.tools}
        tool_rows = (
            {
                t.slug: t
                for t in (
                    await session.scalars(
                        select(Tool)
                        .options(selectinload(Tool.versions), selectinload(Tool.permissions))
                        .where(Tool.id.in_([uuid.UUID(i) for i in resolved.tool_ids.values()]))
                    )
                ).all()
            }
            if resolved.tool_ids
            else {}
        )
        limits = {b.tool_id: b.max_calls_per_run for b in version.tool_bindings}
        calls: dict[str, int] = {}
        produced_artifacts: list[uuid.UUID] = []
        tool_ctx = ToolContext(
            session_factory=self.session_factory,
            storage=self.adapters.storage,
            organization_id=run.organization_id,
            workspace_id=run.workspace_id,
            project_id=run.project_id,
            conversation_id=run.conversation_id,
            run_id=run.id,
            node_run_id=node.id,
            agent_version_id=version.id,
            created_by=run.created_by,
            provider_credentials=credentials,
            settings={},
        )
        executor = tool_registry.bound_executor(tool_ctx)
        artifact_service = ArtifactService(session, None, self.adapters.storage)

        async def invoke_tool(slug: str, args: dict[str, Any]) -> dict[str, Any]:
            spec = bound_tools.get(slug)
            row = tool_rows.get(slug)
            if spec is None or row is None:
                return {
                    "ok": False,
                    "error": "tool_not_allowed",
                    "message": f"{slug} is not enabled for this agent",
                }
            if not _permitted(row.permissions, creator_role, run.workspace_id):
                return {
                    "ok": False,
                    "error": "tool_forbidden",
                    "message": f"{slug} is not permitted for this user",
                }
            limit = limits.get(row.id)
            calls[slug] = calls.get(slug, 0) + 1
            if limit is not None and calls[slug] > limit:
                return {
                    "ok": False,
                    "error": "tool_limit",
                    "message": f"{slug} may be called at most {limit} times per run",
                }
            await recorder.add(
                EventType.TOOL_STARTED,
                SafeEventPayload(
                    node_id=node.node_id,
                    tool_slug=slug,
                    tool_display_name=spec.display_name,
                    input_summary=_summary(redact(str(args)), 300),
                ),
                node_run_id=node.id,
            )
            await recorder.commit()
            tv = next((v for v in row.versions if v.id == row.active_version_id), None)
            tool_spec = ToolSpec(
                slug=slug,
                display_name=spec.display_name,
                description=spec.description,
                input_schema=tv.input_schema if tv else spec.input_schema,
                output_schema=tv.output_schema if tv else None,
                timeout_seconds=tv.timeout_seconds if tv else 60,
            )
            if row.executor_type != "internal_function" or not tool_registry.has(slug):
                result_payload: dict[str, Any] = {
                    "ok": False,
                    "error": "executor_unavailable",
                    "message": f"executor {row.executor_type} is not available in this deployment",
                }
                await recorder.add(
                    EventType.TOOL_COMPLETED,
                    SafeEventPayload(node_id=node.node_id, tool_slug=slug, error_code="executor_unavailable"),
                    node_run_id=node.id,
                )
                await recorder.commit()
                return result_payload
            result = await executor.execute(
                ToolCall(tool=tool_spec, arguments=args, run_id=str(run.id), node_run_id=str(node.id))
            )
            artifact_ids: list[str] = []
            for file in result.files:
                if not isinstance(file, ProducedFile):
                    continue
                parent = file.metadata.get("parent_artifact_id")
                art, av = await artifact_service.persist_produced(
                    file,
                    workspace_id=run.workspace_id,
                    project_id=run.project_id,
                    conversation_id=run.conversation_id,
                    run_id=run.id,
                    node_run_id=node.id,
                    agent_version_id=version.id,
                    organization_id=run.organization_id,
                    created_by=run.created_by,
                    parent_artifact_id=uuid.UUID(str(parent)) if parent else None,
                    status="final" if file.metadata.get("final") else "generated",
                )
                produced_artifacts.append(art.id)
                artifact_ids.append(str(art.id))
                await recorder.add(
                    EventType.ARTIFACT_CREATED,
                    SafeEventPayload(
                        node_id=node.node_id,
                        artifact_id=str(art.id),
                        artifact_type=art.type,
                        artifact_version=av.version_number,
                        output_summary=f"{art.name} ({av.width}x{av.height})" if av.width else art.name,
                    ),
                    node_run_id=node.id,
                )
            await recorder.add(
                EventType.TOOL_COMPLETED,
                SafeEventPayload(
                    node_id=node.node_id,
                    tool_slug=slug,
                    duration_ms=result.duration_ms,
                    error_code=result.error_code,
                    error_message=result.error_message,
                    output_summary=_summary(str(result.output), 300) if result.ok else None,
                ),
                node_run_id=node.id,
            )
            await recorder.commit()
            if not result.ok:
                return {"ok": False, "error": result.error_code, "message": result.error_message}
            return {"ok": True, **result.output, **({"artifact_ids": artifact_ids} if artifact_ids else {})}

        async def emit(event_type: str, payload: dict[str, Any]) -> None:
            return None

        run_input = RunInput(
            user_input=run.input_json.get("body") or run.user_input,
            context_summary=context_summary,
            resume_state=node.resume_state_json,
            clarification_answer=node.answer,
            attachments=list(run.input_json.get("attachments", [])),
        )
        started = datetime.now(UTC)
        outcome: RunOutcome = await asyncio.wait_for(
            runner.run(runtime, run_input, invoke_tool=invoke_tool, emit=emit),
            timeout=version.timeout_seconds,
        )
        duration_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
        session.add(
            ApiUsage(
                organization_id=run.organization_id,
                run_id=run.id,
                node_run_id=node.id,
                provider_type=resolved.provider.type,
                model=runtime.model,
                input_tokens=int(outcome.usage.get("input_tokens", 0)),
                output_tokens=int(outcome.usage.get("output_tokens", 0)),
                tool_calls=sum(calls.values()),
                duration_ms=duration_ms,
            )
        )

        if outcome.requires_clarification:
            node.status = NodeState.WAITING_FOR_USER
            node.question = outcome.question
            node.question_schema = outcome.question_schema
            node.resume_state_json = outcome.resume_state or {}
            node.answer = None
            run.status = RunState.WAITING_FOR_USER
            await recorder.add(
                EventType.CLARIFICATION_REQUESTED,
                SafeEventPayload(
                    node_id=node.node_id,
                    node_name=node.name,
                    node_status=node.status,
                    run_status=run.status,
                    agent_slug=agent.slug,
                    question=outcome.question,
                    question_schema=outcome.question_schema,
                ),
                node_run_id=node.id,
            )
            await recorder.commit()
            return True

        # produced files returned directly by the runner (not via tools)
        for file in outcome.files:
            art, av = await artifact_service.persist_produced(
                file,
                workspace_id=run.workspace_id,
                project_id=run.project_id,
                conversation_id=run.conversation_id,
                run_id=run.id,
                node_run_id=node.id,
                agent_version_id=version.id,
                organization_id=run.organization_id,
                created_by=run.created_by,
            )
            produced_artifacts.append(art.id)
            await recorder.add(
                EventType.ARTIFACT_CREATED,
                SafeEventPayload(
                    node_id=node.node_id,
                    artifact_id=str(art.id),
                    artifact_type=art.type,
                    artifact_version=av.version_number,
                ),
                node_run_id=node.id,
            )

        node.output_json = {
            "output_text": outcome.output_text,
            "structured_output": outcome.structured_output,
            "artifact_ids": [str(a) for a in produced_artifacts],
            "defaults_used": outcome.defaults_used,
            "steps": outcome.steps,
            "tool_calls": calls,
        }
        node.resume_state_json = None

        # QC agent: structured report drives artifact status and the revision loop (spec §16 P7)
        report = parse_report(outcome.structured_output)
        if report is not None:
            node.output_json["qc_passed"] = report.passed
            node.output_json["findings_count"] = len(report.findings)
            checked = [uuid.UUID(a) for a in report.artifact_ids if _is_uuid(a)] or run.input_json.get(
                "last_artifact_ids", []
            )
            for art_id in checked:
                checked_art = await session.get(Artifact, uuid.UUID(str(art_id)))
                if checked_art is None or checked_art.status not in ("generated", "qc_failed"):
                    continue
                checked_art.status = "generated" if report.passed else "qc_failed"
                current = (
                    await session.get(ArtifactVersion, checked_art.current_version_id)
                    if checked_art.current_version_id
                    else None
                )
                if current is not None:
                    current.metadata_json = {**current.metadata_json, "last_qc": report.model_dump()}
            if not report.passed:
                await self._maybe_request_revision(
                    session,
                    run,
                    node,
                    agent,
                    report.failing and [f"{f.code}: {f.message}" for f in report.failing] or [report.summary],
                )
        if produced_artifacts:
            run.input_json = {**run.input_json, "last_artifact_ids": [str(a) for a in produced_artifacts]}
        run.result_json = {
            **run.result_json,
            "output_text": outcome.output_text,
            "last_agent": agent.slug,
            "artifact_ids": list(
                dict.fromkeys(run.result_json.get("artifact_ids", []) + [str(a) for a in produced_artifacts])
            ),
        }

        if node.kind == "manager":
            await self._expand_manager_plan(session, run, node, agent, version, outcome)
        return False

    # ------------------------------------------------------------------ manager delegation (spec §9 example, §13)
    async def _expand_manager_plan(
        self,
        session: AsyncSession,
        run: WorkflowRun,
        node: NodeRun,
        manager: Agent,
        version: AgentVersion,
        outcome: RunOutcome,
    ) -> None:
        handoff_targets = [h.target_agent_id for h in version.handoffs]
        if not handoff_targets:
            return
        targets = {
            a.id: a
            for a in (
                await session.scalars(
                    select(Agent).where(Agent.id.in_(handoff_targets), Agent.status == "active")
                )
            ).all()
        }
        by_command = {a.command: a for a in targets.values()}
        steps: list[dict[str, Any]] = []
        structured = outcome.structured_output or {}
        plan = structured.get("plan") if isinstance(structured, dict) else None
        if isinstance(plan, list):
            for item in plan:
                if not isinstance(item, dict):
                    continue
                cmd = str(item.get("command") or item.get("agent") or "").strip().lower()
                cmd = cmd if cmd.startswith("/") else f"/{cmd}"
                if cmd in by_command:
                    steps.append(
                        {
                            "agent": by_command[cmd],
                            "instruction": str(item.get("instruction") or item.get("task") or ""),
                        }
                    )
        if not steps:
            steps = _heuristic_plan(run.user_input, version, targets)
        existing_ids = {n.node_id for n in run.nodes}
        next_index = max((n.index for n in run.nodes if n.index < SAVE_NODE_INDEX), default=node.index) + 1
        added = []
        for i, step in enumerate(steps[:12]):
            target = step["agent"]
            node_id = f"agent:{target.slug}:{i + 1}"
            if node_id in existing_ids:
                continue
            session.add(
                NodeRun(
                    run_id=run.id,
                    node_id=node_id,
                    index=next_index,
                    name=target.name,
                    kind="agent",
                    status=NodeState.PENDING,
                    agent_id=target.id,
                    agent_version_id=target.active_version_id,
                    input_json={"instruction": step.get("instruction", ""), "delegated_by": manager.slug},
                )
            )
            added.append(
                {
                    "id": node_id,
                    "name": target.name,
                    "kind": "agent",
                    "index": next_index,
                    "agent_slug": target.slug,
                }
            )
            next_index += 1
        if added:
            run.plan_json = (
                [n for n in run.plan_json if n["kind"] != "save"]
                + added
                + [n for n in run.plan_json if n["kind"] == "save"]
            )
            node.output_json = {
                **node.output_json,
                "plan": [{"agent": a["agent_slug"], "node_id": a["id"]} for a in added],
            }
        await session.flush()

    async def _maybe_request_revision(
        self, session: AsyncSession, run: WorkflowRun, qc_node: NodeRun, qc_agent: Agent, findings: list[str]
    ) -> None:
        """QC failed: send the artifact back to the producing agent once (configurable), then QC again."""
        revisions = int(run.input_json.get("revisions", 0))
        max_revisions = int(run.input_json.get("max_revisions", 1))
        if revisions >= max_revisions:
            run.result_json = {**run.result_json, "qc_exhausted": True}
            return
        producer = None
        for n in sorted(run.nodes, key=lambda n: n.index, reverse=True):
            if (
                n.kind == "agent"
                and n.status == NodeState.SUCCEEDED
                and n.agent_id != qc_agent.id
                and n.index < qc_node.index
            ):
                producer = n
                break
        if producer is None:
            return
        next_index = max((n.index for n in run.nodes if n.index < SAVE_NODE_INDEX), default=qc_node.index) + 1
        rev = revisions + 1
        session.add(
            NodeRun(
                run_id=run.id,
                node_id=f"{producer.node_id}:rev{rev}",
                index=next_index,
                name=f"{producer.name} (revision {rev})",
                kind="agent",
                status=NodeState.PENDING,
                agent_id=producer.agent_id,
                agent_version_id=producer.agent_version_id,
                input_json={**producer.input_json, "qc_findings": findings, "revision": rev},
            )
        )
        session.add(
            NodeRun(
                run_id=run.id,
                node_id=f"{qc_node.node_id}:rev{rev}",
                index=next_index + 1,
                name=f"{qc_node.name} (re-check {rev})",
                kind="agent",
                status=NodeState.PENDING,
                agent_id=qc_node.agent_id,
                agent_version_id=qc_node.agent_version_id,
                input_json={**qc_node.input_json, "revision": rev},
            )
        )
        run.input_json = {**run.input_json, "revisions": rev}
        await session.flush()

    async def _save_result(
        self, session: AsyncSession, run: WorkflowRun, node: NodeRun, conversation: Conversation
    ) -> None:
        agent_nodes = [
            n
            for n in sorted(run.nodes, key=lambda n: n.index)
            if n.kind in ("agent", "manager") and n.status == NodeState.SUCCEEDED
        ]
        parts: list[str] = []
        artifact_ids: list[uuid.UUID] = []
        last_agent_id: uuid.UUID | None = None
        last_version_id: uuid.UUID | None = None
        for n in agent_nodes:
            text = str(n.output_json.get("output_text", "")).strip()
            if text:
                parts.append(text if len(agent_nodes) == 1 else f"**{n.name}**\n{text}")
            artifact_ids.extend(uuid.UUID(a) for a in n.output_json.get("artifact_ids", []))
            defaults = n.output_json.get("defaults_used") or []
            if defaults:
                parts.append("_Defaults used: " + "; ".join(str(d) for d in defaults) + "_")
            last_agent_id, last_version_id = n.agent_id, n.agent_version_id
        content = "\n\n".join(parts) or "(no output)"
        agent = await session.get(Agent, last_agent_id) if last_agent_id else None
        await ConversationService(session, None).add_assistant_message(
            conversation.id,
            content=content,
            agent=agent,
            agent_version_id=last_version_id,
            run_id=run.id,
            artifact_ids=list(dict.fromkeys(artifact_ids)),
            metadata={"nodes": len(agent_nodes)},
        )
        run.result_json = {
            **run.result_json,
            "output_text": content,
            "artifact_ids": [str(a) for a in dict.fromkeys(artifact_ids)],
        }
        node.output_json = {"message_chars": len(content), "artifacts": len(artifact_ids)}


def _permitted(permissions: list[ToolPermission], role: str | None, workspace_id: uuid.UUID) -> bool:
    if not permissions:
        return True
    allowed = False
    restricted = False
    for p in permissions:
        if p.subject_type == "role":
            restricted = True
            if p.allowed and has_at_least(role, Role(p.subject_key)) if role else False:
                allowed = True
            if not p.allowed and role == p.subject_key:
                return False
        elif p.subject_type == "workspace":
            restricted = True
            if str(workspace_id) == p.subject_key:
                if not p.allowed:
                    return False
                allowed = True
    return allowed or not restricted


def _is_uuid(value: Any) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, TypeError):
        return False


def _heuristic_plan(
    user_input: str, version: AgentVersion, targets: dict[uuid.UUID, Agent]
) -> list[dict[str, Any]]:
    """Deterministic fallback when the manager model returns no structured plan."""
    text = user_input.lower()
    ordered = [
        targets[h.target_agent_id]
        for h in version.handoffs
        if h.target_agent_id in targets and not h.is_failure_route
    ]
    hints = {h.target_agent_id: h.routing_hint for h in version.handoffs}
    chosen: list[dict[str, Any]] = []
    for agent in ordered:
        words = {
            agent.command.strip("/"),
            agent.slug.split("-")[0],
            *(w for w in re.findall(r"[a-z]{4,}", (hints.get(agent.id) or "").lower())),
        }
        if any(re.search(rf"\b{re.escape(w)}", text) for w in words if w):
            chosen.append(
                {"agent": agent, "instruction": f"Handle the '{agent.command}' part of: {user_input[:300]}"}
            )
    if not chosen and ordered:
        chosen = [{"agent": ordered[0], "instruction": user_input[:300]}]
    return chosen
