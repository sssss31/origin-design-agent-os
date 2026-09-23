"""Agent Gateway (Origin Agent Workspace V0 §7): one generic path to any existing agent.

    call_agent(agent, message, conversation, files)
      1. read agent configuration        2. resolve API credential
      3. load conversation context       4. attach required files
      5. call the existing agent API     6. stream the response
      7. return the reply (the executor saves message, artifacts and session id)

No system prompt is composed here: the existing agent keeps its own instructions (§8).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.adapters.registry import Adapters
from app.core.config import Settings
from app.models.agents import Agent
from app.models.chat import AgentSession, Message
from app.models.files import Artifact, Asset
from app.ports.storage import ObjectStorage
from app.providers.base import ConnectionTest
from app.providers.existing.base import AgentCallError, AgentConnection, AgentFile, AgentReply, OnDelta
from app.providers.existing.registry import build_existing_providers

HISTORY_LIMIT = 12  # bounded Origin-side context when the agent has no native session (§11)
HISTORY_CHARS = 12_000


@dataclass(slots=True)
class GatewayContext:
    history: list[dict[str, str]] = field(default_factory=list)
    session_id: str | None = None
    session_native: bool = False


async def resolve_connection(agent: Agent, adapters: Adapters) -> AgentConnection:
    api_key: str | None = None
    if agent.api_key_secret_ref_id:
        try:
            api_key = await adapters.secrets.reveal(str(agent.api_key_secret_ref_id))
        except LookupError as exc:
            raise AgentCallError(
                "agent_not_configured", f"{agent.name}: the stored credential cannot be read."
            ) from exc
    return AgentConnection(
        agent_slug=agent.slug,
        agent_name=agent.name,
        connection_type=agent.connection_type,
        endpoint=agent.api_endpoint,
        api_key=api_key,
        config=dict(agent.connection_config or {}),
    )


async def load_context(
    session: AsyncSession, *, conversation_id: uuid.UUID, agent: Agent, exclude_message_id: uuid.UUID | None
) -> GatewayContext:
    """Native session when the agent API keeps one (§10); otherwise bounded recent messages (§11)."""
    ctx = GatewayContext()
    row = await session.scalar(
        select(AgentSession).where(
            AgentSession.conversation_id == conversation_id, AgentSession.agent_id == agent.id
        )
    )
    if row is not None and row.provider_session_id:
        ctx.session_id = row.provider_session_id
        ctx.session_native = True
        return ctx
    q = (
        select(Message)
        .where(Message.conversation_id == conversation_id, Message.role.in_(["user", "assistant"]))
        .order_by(Message.created_at.desc())
        .limit(HISTORY_LIMIT * 2)
    )
    if exclude_message_id is not None:
        q = q.where(Message.id != exclude_message_id)
    rows = list((await session.scalars(q)).all())
    rows.reverse()
    total = 0
    history: list[dict[str, str]] = []
    for m in reversed(rows):  # newest first, then reverse again
        if m.role == "assistant" and m.agent_id not in (None, agent.id):
            # another agent's answer: keep a short reference only (§12)
            text = f"[{m.metadata_json.get('agent_name', 'another agent')}] " + m.content.strip()[:400]
        else:
            text = m.content.strip()[:2000]
        if total + len(text) > HISTORY_CHARS or len(history) >= HISTORY_LIMIT:
            break
        history.append({"role": "user" if m.role == "user" else "assistant", "content": text})
        total += len(text)
    history.reverse()
    ctx.history = history
    return ctx


async def prepare_files(
    session: AsyncSession,
    storage: ObjectStorage,
    *,
    asset_ids: list[uuid.UUID],
    artifact_ids: list[uuid.UUID],
    settings: Settings,
) -> list[AgentFile]:
    files: list[AgentFile] = []
    if asset_ids:
        assets = (
            await session.scalars(
                select(Asset).options(selectinload(Asset.versions)).where(Asset.id.in_(asset_ids))
            )
        ).all()
        for a in assets:
            v = next((x for x in a.versions if x.id == a.current_version_id), None)
            if v is None:
                continue
            content = await storage.get(v.storage_key)
            url = await storage.presign_download(
                v.storage_key, expires_in=settings.signed_url_ttl_seconds, filename=a.name
            )
            files.append(AgentFile(name=a.name, mime_type=v.mime_type, content=content, url=url))
    if artifact_ids:
        arts = (
            await session.scalars(
                select(Artifact).options(selectinload(Artifact.versions)).where(Artifact.id.in_(artifact_ids))
            )
        ).all()
        for art in arts:
            av = next((x for x in art.versions if x.id == art.current_version_id), None)
            if av is None:
                continue
            content = await storage.get(av.storage_key)
            url = await storage.presign_download(
                av.storage_key, expires_in=settings.signed_url_ttl_seconds, filename=art.name
            )
            files.append(AgentFile(name=art.name, mime_type=av.mime_type, content=content, url=url))
    return files


async def call_agent(
    *,
    agent: Agent,
    message: str,
    conversation_id: uuid.UUID,
    context: GatewayContext,
    files: list[AgentFile],
    adapters: Adapters,
    settings: Settings,
    on_delta: OnDelta,
    transport: Any = None,
) -> AgentReply:
    providers = build_existing_providers(settings, transport=transport)
    provider = providers.get(agent.connection_type)
    if provider is None:
        raise AgentCallError("agent_not_configured", f"{agent.name} has no supported connection type.")
    conn = await resolve_connection(agent, adapters)
    try:
        return await provider.send_message(
            conn,
            message,
            history=context.history,
            files=files,
            session_id=context.session_id,
            conversation_id=str(conversation_id),
            on_delta=on_delta,
        )
    except AgentCallError as exc:
        if exc.code == "agent_session_lost" and context.session_id:
            # the agent's native session expired: retry once from Origin's own context
            context.session_id = None
            context.session_native = False
            return await provider.send_message(
                conn,
                message,
                history=context.history,
                files=files,
                session_id=None,
                conversation_id=str(conversation_id),
                on_delta=on_delta,
            )
        raise


async def test_agent_connection(
    agent: Agent, adapters: Adapters, settings: Settings, *, transport: Any = None
) -> ConnectionTest:
    providers = build_existing_providers(settings, transport=transport)
    provider = providers.get(agent.connection_type)
    if provider is None:
        return ConnectionTest(ok=False, message=f"unsupported connection type {agent.connection_type}")
    conn = await resolve_connection(agent, adapters)
    return await provider.test_connection(conn)
