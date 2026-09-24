"""Admin console endpoints (docs/ADMIN_CONSOLE.md): overview, activity log, agent test message,
agent deletion. Read-mostly views over agents / workflow_runs; nothing here reveals credentials."""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.admin import AdminAuth
from app.core.authz import DB, Config
from app.core.deps import AdaptersDep
from app.core.errors import Conflict, NotFound
from app.models.agents import Agent
from app.models.chat import Conversation, Message
from app.models.identity import Organization
from app.models.workflows import WorkflowRun
from app.providers.existing.base import AgentCallError
from app.services import audit
from app.services.agent_gateway import GatewayContext, call_agent

router = APIRouter()


class ActivityRunOut(BaseModel):
    run_id: uuid.UUID
    conversation_id: uuid.UUID
    conversation_title: str
    agent_id: uuid.UUID | None
    agent_name: str | None
    agent_command: str | None
    status: str
    user_input: str
    error_code: str | None
    error_message: str | None
    duration_ms: int | None
    created_at: datetime
    finished_at: datetime | None


class OverviewOut(BaseModel):
    agents_total: int
    agents_connected: int
    agents_failing: int
    agents_without_key: int
    agents_disabled: int
    runs_24h: int
    runs_24h_succeeded: int
    runs_24h_failed: int
    avg_latency_ms_24h: int | None
    recent_failures: list[ActivityRunOut]
    default_agent_id: uuid.UUID | None


class MessageTestIn(BaseModel):
    message: str = Field(min_length=1, max_length=20000)


class MessageTestOut(BaseModel):
    ok: bool
    reply: str | None
    latency_ms: int
    session_native: bool
    files_count: int
    error_code: str | None = None
    error_message: str | None = None


def _duration_ms(run: WorkflowRun) -> int | None:
    if run.started_at and run.finished_at:
        return int((run.finished_at - run.started_at).total_seconds() * 1000)
    return None


async def _activity(
    session: AsyncSession,
    org_id: uuid.UUID,
    *,
    agent_id: uuid.UUID | None = None,
    run_status: str | None = None,
    limit: int = 50,
) -> list[ActivityRunOut]:
    q = (
        select(WorkflowRun, Conversation.title, Agent.name, Agent.command)
        .join(Conversation, Conversation.id == WorkflowRun.conversation_id)
        .outerjoin(Agent, Agent.id == WorkflowRun.entry_agent_id)
        .where(WorkflowRun.organization_id == org_id)
    )
    if agent_id is not None:
        q = q.where(WorkflowRun.entry_agent_id == agent_id)
    if run_status:
        q = q.where(WorkflowRun.status == run_status.upper())
    q = q.order_by(WorkflowRun.created_at.desc()).limit(limit)
    rows = (await session.execute(q)).all()
    out: list[ActivityRunOut] = []
    for run, title, agent_name, agent_command in rows:
        err = run.error_json or {}
        out.append(
            ActivityRunOut(
                run_id=run.id,
                conversation_id=run.conversation_id,
                conversation_title=title,
                agent_id=run.entry_agent_id,
                agent_name=agent_name,
                agent_command=agent_command,
                status=run.status,
                user_input=(run.user_input or "")[:200],
                error_code=err.get("code"),
                error_message=err.get("message"),
                duration_ms=_duration_ms(run),
                created_at=run.created_at,
                finished_at=run.finished_at,
            )
        )
    return out


@router.get("/overview", response_model=OverviewOut)
async def overview(ctx: AdminAuth, session: DB) -> OverviewOut:
    org_id = ctx.require_organization()
    agents = list(
        await session.scalars(
            select(Agent).where(Agent.organization_id == org_id, Agent.is_manager.is_(False))
        )
    )
    external = [a for a in agents if a.connection_type != "origin"]
    since = datetime.now(UTC) - timedelta(hours=24)
    runs = list(
        await session.scalars(
            select(WorkflowRun).where(WorkflowRun.organization_id == org_id, WorkflowRun.created_at >= since)
        )
    )
    durations = [d for d in (_duration_ms(r) for r in runs) if d is not None]
    org = await session.get(Organization, org_id)
    default_ref = (org.settings_json or {}).get("default_agent_id") if org else None
    return OverviewOut(
        agents_total=len(agents),
        agents_connected=sum(a.connection_status == "ok" for a in external),
        agents_failing=sum(a.connection_status == "error" for a in external),
        agents_without_key=sum(a.api_key_secret_ref_id is None for a in external),
        agents_disabled=sum(a.status != "active" for a in agents),
        runs_24h=len(runs),
        runs_24h_succeeded=sum(r.status == "SUCCEEDED" for r in runs),
        runs_24h_failed=sum(r.status == "FAILED" for r in runs),
        avg_latency_ms_24h=int(sum(durations) / len(durations)) if durations else None,
        recent_failures=await _activity(session, org_id, run_status="FAILED", limit=8),
        default_agent_id=uuid.UUID(str(default_ref)) if default_ref else None,
    )


@router.get("/activity", response_model=list[ActivityRunOut])
async def activity(
    ctx: AdminAuth,
    session: DB,
    agent_id: uuid.UUID | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ActivityRunOut]:
    return await _activity(
        session, ctx.require_organization(), agent_id=agent_id, run_status=status_filter, limit=limit
    )


async def _agent(session: AsyncSession, org_id: uuid.UUID, agent_id: uuid.UUID) -> Agent:
    agent = await session.get(Agent, agent_id)
    if agent is None or agent.organization_id != org_id:
        raise NotFound("Agent not found", code="agent_not_found")
    return agent


@router.post("/agents/{agent_id}/test-message", response_model=MessageTestOut)
async def test_message(
    agent_id: uuid.UUID,
    body: MessageTestIn,
    ctx: AdminAuth,
    session: DB,
    adapters: AdaptersDep,
    settings: Config,
) -> MessageTestOut:
    """Send one message through the same gateway the chat uses, without creating a chat.
    Failures come back as data so the admin sees exactly what a user would see."""
    agent = await _agent(session, ctx.require_organization(), agent_id)
    if agent.connection_type == "origin":
        return MessageTestOut(
            ok=False,
            reply=None,
            latency_ms=0,
            session_native=False,
            files_count=0,
            error_code="origin_hosted",
            error_message="Origin-hosted agents are tested from the Advanced editor.",
        )
    started = datetime.now(UTC)

    async def _noop(_: str) -> None:
        return None

    try:
        reply = await asyncio.wait_for(
            call_agent(
                agent=agent,
                message=body.message,
                conversation_id=uuid.uuid4(),
                context=GatewayContext(),
                files=[],
                adapters=adapters,
                settings=settings,
                on_delta=_noop,
                transport=getattr(adapters, "http_transport", None),
            ),
            timeout=float((agent.connection_config or {}).get("timeout_seconds") or 120),
        )
    except AgentCallError as exc:
        agent.connection_status = "error"
        agent.connection_message = exc.message
        agent.connection_tested_at = datetime.now(UTC)
        return MessageTestOut(
            ok=False,
            reply=None,
            latency_ms=int((datetime.now(UTC) - started).total_seconds() * 1000),
            session_native=False,
            files_count=0,
            error_code=exc.code,
            error_message=exc.message,
        )
    except TimeoutError:
        return MessageTestOut(
            ok=False,
            reply=None,
            latency_ms=int((datetime.now(UTC) - started).total_seconds() * 1000),
            session_native=False,
            files_count=0,
            error_code="agent_timeout",
            error_message=f"{agent.name} did not answer in time.",
        )
    latency = int((datetime.now(UTC) - started).total_seconds() * 1000)
    agent.connection_status = "ok"
    agent.connection_message = f"Replied in {latency} ms"
    agent.connection_tested_at = datetime.now(UTC)
    return MessageTestOut(
        ok=True,
        reply=reply.text,
        latency_ms=latency,
        session_native=bool(reply.session_id),
        files_count=len(reply.files),
    )


@router.delete("/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(agent_id: uuid.UUID, ctx: AdminAuth, session: DB, adapters: AdaptersDep) -> None:
    """Hard delete is only allowed for an agent that was never used; otherwise disable it so the
    chat history keeps pointing at a real agent."""
    org_id = ctx.require_organization()
    agent = await _agent(session, org_id, agent_id)
    used_runs = await session.scalar(
        select(func.count()).select_from(WorkflowRun).where(WorkflowRun.entry_agent_id == agent.id)
    )
    used_messages = await session.scalar(
        select(func.count()).select_from(Message).where(Message.agent_id == agent.id)
    )
    if used_runs or used_messages:
        raise Conflict(
            "This agent has already been used in chats; disable it instead of deleting it.",
            code="agent_in_use",
        )
    secret_ref = agent.api_key_secret_ref_id
    before = {"name": agent.name, "command": agent.command, "connection_type": agent.connection_type}
    agent.api_key_secret_ref_id = None
    await session.flush()
    try:
        await session.delete(agent)
        await session.flush()
    except IntegrityError as exc:
        raise Conflict(
            "This agent is referenced by another agent's handoffs; remove those first.",
            code="agent_in_use",
        ) from exc
    await audit.record(
        session,
        action="agent.deleted",
        entity_type="agent",
        entity_id=agent_id,
        organization_id=org_id,
        actor_user_id=ctx.user_id,
        before=before,
        request_id=ctx.request_id,
    )
    await session.commit()
    if secret_ref:
        # the agent row is gone; an orphaned ciphertext is harmless, so a store hiccup is not an error
        with contextlib.suppress(Exception):
            await adapters.secrets.delete(str(secret_ref))
