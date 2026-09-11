"""Run lifecycle from the API side: create (route + plan + enqueue), clarification resume,
cancel, retry, read (spec §9, §11, §12)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.adapters.registry import Adapters
from app.core.authz import AuthContext
from app.core.config import Settings
from app.core.errors import NotFound, RateLimited, ValidationFailed
from app.domain.events import EventType, SafeEventPayload
from app.domain.roles import Role
from app.domain.run_state import NodeState, RunState, assert_run_transition
from app.domain.slash import parse_message
from app.models.chat import Conversation, Message
from app.models.identity import Organization
from app.models.workflows import NodeRun, WorkflowRun
from app.ports.queue import Job
from app.schemas.chat import MessageCreate
from app.schemas.runs import ClarificationAnswer, RunCreate
from app.services import audit
from app.services.access import ProjectAccess, resolve_project
from app.services.conversations import ConversationService
from app.services.events import EventRecorder
from app.services.router import resolve_route

JOB_TYPE = "run.execute"
SAVE_NODE_INDEX = 1000


def plan_for(agent_slug: str, agent_name: str, *, is_manager: bool) -> list[dict]:
    """V0 sequential plan (spec §16 P5: Parse → Context → Agent → Save Result)."""
    return [
        {"id": "parse", "name": "Parse command", "kind": "parse", "index": 0},
        {"id": "context", "name": "Load context", "kind": "context", "index": 1},
        {
            "id": f"agent:{agent_slug}",
            "name": agent_name,
            "kind": "manager" if is_manager else "agent",
            "index": 2,
            "agent_slug": agent_slug,
        },
        {"id": "save", "name": "Save result", "kind": "save", "index": SAVE_NODE_INDEX},
    ]


class RunService:
    def __init__(
        self, session: AsyncSession, ctx: AuthContext, adapters: Adapters, settings: Settings
    ) -> None:
        self.session = session
        self.ctx = ctx
        self.adapters = adapters
        self.settings = settings

    # ------------------------------------------------------------------ helpers
    async def _run(
        self, run_id: uuid.UUID, required: Role = Role.VIEWER
    ) -> tuple[WorkflowRun, ProjectAccess]:
        run = await self.session.scalar(
            select(WorkflowRun)
            .options(selectinload(WorkflowRun.nodes))
            .where(WorkflowRun.id == run_id)
            .execution_options(populate_existing=True)
        )
        if run is None:
            raise NotFound("Run not found", code="run_not_found")
        access = await resolve_project(self.session, self.ctx, run.project_id)
        access.require(required)
        return run, access

    async def _check_quota(self, org_id: uuid.UUID) -> None:
        org = await self.session.get(Organization, org_id)
        limit = (
            int((org.settings_json or {}).get("quota_runs_per_day", self.settings.default_runs_per_day))
            if org
            else self.settings.default_runs_per_day
        )
        if limit <= 0:
            return
        since = datetime.now(UTC) - timedelta(days=1)
        count = await self.session.scalar(
            select(func.count(WorkflowRun.id)).where(
                WorkflowRun.organization_id == org_id, WorkflowRun.created_at >= since
            )
        )
        if (count or 0) >= limit:
            raise RateLimited(
                f"Organization quota of {limit} runs per day reached",
                code="quota_exceeded",
                details={"limit": limit, "window": "24h"},
            )

    async def _enqueue(self, run_id: uuid.UUID) -> None:
        await self.adapters.queue.enqueue(
            Job(
                type=JOB_TYPE,
                payload={"run_id": str(run_id)},
                idempotency_key=f"run:{run_id}:{uuid.uuid4().hex[:8]}",
            )
        )

    def stream_url(self, run_id: uuid.UUID) -> str:
        return f"{self.settings.api_prefix}/runs/{run_id}/events"

    # ------------------------------------------------------------------ create
    async def create(self, conversation_id: uuid.UUID, data: RunCreate) -> WorkflowRun:
        conv = await self.session.get(Conversation, conversation_id)
        if conv is None:
            raise NotFound("Conversation not found", code="conversation_not_found")
        access = await resolve_project(self.session, self.ctx, conv.project_id)
        access.require(Role.MEMBER)
        org_id = access.workspace.organization_id
        await self._check_quota(org_id)

        message: Message | None = None
        if data.message_id is not None:
            message = await self.session.get(Message, data.message_id)
            if message is None or message.conversation_id != conv.id:
                raise NotFound("Message not found in this conversation", code="message_not_found")
            if message.run_id is not None:
                raise ValidationFailed(
                    "This message already has a run",
                    code="message_already_run",
                    details={"run_id": str(message.run_id)},
                )
        elif data.content:
            message = await ConversationService(self.session, self.ctx).add_user_message(
                conv.id,
                MessageCreate(
                    content=data.content,
                    asset_ids=data.selected_asset_ids,
                    artifact_ids=data.selected_artifact_ids,
                ),
            )
        else:
            raise ValidationFailed("Provide message_id or content", code="missing_input")

        parsed = parse_message(message.content)
        route = await resolve_route(
            self.session,
            org_id,
            parsed,
            command_override=data.command,
            preferred_agent_id=data.preferred_agent_id,
        )
        run = WorkflowRun(
            organization_id=org_id,
            workspace_id=access.workspace.id,
            project_id=conv.project_id,
            conversation_id=conv.id,
            message_id=message.id,
            status=RunState.QUEUED,
            command=route.command,
            user_input=message.content,
            entry_agent_id=route.agent.id,
            plan_json=plan_for(
                route.agent.slug,
                route.agent.name,
                is_manager=route.agent.is_manager and not route.explicit or route.agent.is_manager,
            ),
            input_json={
                "selected_asset_ids": [str(a) for a in data.selected_asset_ids]
                or [str(a.asset_id) for a in message.attachments if a.asset_id],
                "selected_artifact_ids": [str(a) for a in data.selected_artifact_ids]
                or [str(a.artifact_id) for a in message.attachments if a.artifact_id],
                "options": data.options,
                "body": parsed.body,
                "explicit": route.explicit,
                "revisions": 0,
                "max_revisions": int(data.options.get("max_revisions", self.settings.default_max_revisions)),
            },
            created_by=self.ctx.user_id,
        )
        self.session.add(run)
        await self.session.flush()
        for node in run.plan_json:
            self.session.add(
                NodeRun(
                    run_id=run.id,
                    node_id=node["id"],
                    index=node["index"],
                    name=node["name"],
                    kind=node["kind"],
                    status=NodeState.PENDING,
                    agent_id=route.agent.id if node["kind"] in ("agent", "manager") else None,
                    agent_version_id=route.version.id if node["kind"] in ("agent", "manager") else None,
                )
            )
        message.run_id = run.id
        await self.session.flush()
        await audit.record(
            self.session,
            action="run.created",
            entity_type="workflow_run",
            entity_id=run.id,
            organization_id=org_id,
            actor_user_id=self.ctx.user_id,
            after={"command": route.command, "agent": route.agent.slug, "explicit": route.explicit},
            request_id=self.ctx.request_id,
        )
        await self.session.commit()  # the worker must see the run before the job starts
        await self._enqueue(run.id)
        run, _ = await self._run(run.id)
        return run

    # ------------------------------------------------------------------ reads
    async def get(self, run_id: uuid.UUID) -> WorkflowRun:
        run, _ = await self._run(run_id)
        return run

    async def list_for_conversation(self, conversation_id: uuid.UUID, limit: int = 50) -> list[WorkflowRun]:
        conv = await self.session.get(Conversation, conversation_id)
        if conv is None:
            raise NotFound("Conversation not found", code="conversation_not_found")
        await resolve_project(self.session, self.ctx, conv.project_id)
        rows = await self.session.scalars(
            select(WorkflowRun)
            .options(selectinload(WorkflowRun.nodes))
            .where(WorkflowRun.conversation_id == conversation_id)
            .order_by(WorkflowRun.created_at.desc())
            .limit(limit)
        )
        return list(rows.all())

    # ------------------------------------------------------------------ clarification resume (spec §3)
    async def answer_clarification(self, run_id: uuid.UUID, data: ClarificationAnswer) -> WorkflowRun:
        run, access = await self._run(run_id, Role.MEMBER)
        if run.status != RunState.WAITING_FOR_USER:
            raise ValidationFailed(
                "Run is not waiting for a clarification",
                code="run_not_waiting",
                details={"status": run.status},
            )
        node = next((n for n in run.nodes if n.status == NodeState.WAITING_FOR_USER), None)
        if node is None:
            raise ValidationFailed("No node is waiting", code="run_not_waiting")
        node.answer = data.answer
        node.input_json = {**node.input_json, "clarification_data": data.data}
        run.status = assert_run_transition(run.status, RunState.QUEUED)
        # the reply is part of the conversation, linked to the run
        reply = Message(
            conversation_id=run.conversation_id,
            role="user",
            content=data.answer,
            run_id=run.id,
            author_user_id=self.ctx.user_id,
            metadata_json={"clarification_answer": True, "node_id": node.node_id},
        )
        self.session.add(reply)
        recorder = EventRecorder(self.session, self.adapters.events, run.id)
        await recorder.add(
            EventType.CLARIFICATION_RECEIVED,
            SafeEventPayload(
                node_id=node.node_id,
                node_name=node.name,
                node_status=node.status,
                run_status=run.status,
                input_summary=data.answer[:500],
            ),
            node_run_id=node.id,
        )
        await audit.record(
            self.session,
            action="run.clarification_answered",
            entity_type="workflow_run",
            entity_id=run.id,
            organization_id=access.workspace.organization_id,
            actor_user_id=self.ctx.user_id,
            request_id=self.ctx.request_id,
        )
        await recorder.commit()
        await self._enqueue(run.id)
        run, _ = await self._run(run.id)
        return run

    # ------------------------------------------------------------------ cancel / retry (spec §19)
    async def cancel(self, run_id: uuid.UUID) -> WorkflowRun:
        run, access = await self._run(run_id, Role.MEMBER)
        if run.status in (RunState.SUCCEEDED, RunState.FAILED, RunState.CANCELLED):
            raise ValidationFailed(f"Run is already {run.status}", code="run_finished")
        run.cancel_requested = True
        recorder = EventRecorder(self.session, self.adapters.events, run.id)
        if run.status in (RunState.QUEUED, RunState.WAITING_FOR_USER):
            run.status = assert_run_transition(run.status, RunState.CANCELLED)
            run.finished_at = datetime.now(UTC)
            for node in run.nodes:
                if node.status in (NodeState.PENDING, NodeState.WAITING_FOR_USER):
                    node.status = NodeState.SKIPPED
            await recorder.add(EventType.RUN_CANCELLED, SafeEventPayload(run_status=run.status))
        await audit.record(
            self.session,
            action="run.cancel_requested",
            entity_type="workflow_run",
            entity_id=run.id,
            organization_id=access.workspace.organization_id,
            actor_user_id=self.ctx.user_id,
            request_id=self.ctx.request_id,
        )
        await recorder.commit()
        run, _ = await self._run(run.id)
        return run

    async def retry(self, run_id: uuid.UUID) -> WorkflowRun:
        run, access = await self._run(run_id, Role.MEMBER)
        if run.status != RunState.FAILED:
            raise ValidationFailed("Only failed runs can be retried", code="run_not_failed")
        failed = [n for n in run.nodes if n.status == NodeState.FAILED]
        if any(not (n.error_json or {}).get("retryable", True) for n in failed):
            raise ValidationFailed("The failed step is not retryable", code="not_retryable")
        for node in failed:
            node.status = NodeState.PENDING
            node.attempt += 1
            node.error_json = None
        run.status = assert_run_transition(run.status, RunState.QUEUED)
        run.attempt += 1
        run.error_json = None
        run.finished_at = None
        run.cancel_requested = False
        await audit.record(
            self.session,
            action="run.retried",
            entity_type="workflow_run",
            entity_id=run.id,
            organization_id=access.workspace.organization_id,
            actor_user_id=self.ctx.user_id,
            request_id=self.ctx.request_id,
        )
        await self.session.commit()
        await self._enqueue(run.id)
        run, _ = await self._run(run.id)
        return run
