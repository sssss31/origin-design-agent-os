"""Conversations + messages (spec §7, §11 chat API)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.authz import AuthContext
from app.core.errors import NotFound, ValidationFailed
from app.domain.roles import Role
from app.domain.slash import parse_message
from app.models.agents import Agent
from app.models.chat import Conversation, Message, MessageAttachment
from app.models.files import Artifact, Asset
from app.schemas.chat import (
    AttachmentOut,
    ConversationCreate,
    ConversationOut,
    ConversationUpdate,
    MessageCreate,
    MessageOut,
)
from app.schemas.common import from_orm
from app.services import audit
from app.services.access import ProjectAccess, resolve_project


class ConversationService:
    def __init__(self, session: AsyncSession, ctx: AuthContext | None) -> None:
        self.session = session
        self.ctx = ctx

    def _require_ctx(self) -> AuthContext:
        if self.ctx is None:
            raise PermissionError("this operation requires an authenticated context")
        return self.ctx

    async def _conversation(
        self, conversation_id: uuid.UUID, required: Role = Role.VIEWER
    ) -> tuple[Conversation, ProjectAccess]:
        conv = await self.session.get(Conversation, conversation_id)
        if conv is None:
            raise NotFound("Conversation not found", code="conversation_not_found")
        access = await resolve_project(self.session, self._require_ctx(), conv.project_id)
        access.require(required)
        return conv, access

    async def list_for_project(
        self, project_id: uuid.UUID, *, include_archived: bool = False, search: str | None = None
    ) -> list[Conversation]:
        await resolve_project(self.session, self._require_ctx(), project_id)
        q = select(Conversation).where(Conversation.project_id == project_id)
        if not include_archived:
            q = q.where(Conversation.status == "active")
        if search:
            q = q.where(Conversation.title.ilike(f"%{search}%"))
        q = q.order_by(Conversation.last_message_at.desc().nulls_last(), Conversation.created_at.desc())
        return list((await self.session.scalars(q)).all())

    async def create(self, project_id: uuid.UUID, data: ConversationCreate) -> Conversation:
        access = await resolve_project(self.session, self._require_ctx(), project_id)
        access.require(Role.MEMBER)
        conv = Conversation(
            project_id=project_id, title=data.title or "New chat", created_by=self._require_ctx().user_id
        )
        self.session.add(conv)
        await self.session.flush()
        await self.session.refresh(conv)
        return conv

    async def get(self, conversation_id: uuid.UUID) -> tuple[Conversation, ProjectAccess]:
        return await self._conversation(conversation_id)

    async def update(self, conversation_id: uuid.UUID, data: ConversationUpdate) -> Conversation:
        conv, _ = await self._conversation(conversation_id, Role.MEMBER)
        changes = data.model_dump(exclude_unset=True)
        if changes.get("status") == "archived":
            conv.archived_at = datetime.now(UTC)
        elif changes.get("status") == "active":
            conv.archived_at = None
        for k, v in changes.items():
            if v is not None:
                setattr(conv, k, v)
        await self.session.flush()
        await self.session.refresh(conv)
        return conv

    async def messages(
        self, conversation_id: uuid.UUID, *, limit: int = 200, before: datetime | None = None
    ) -> list[Message]:
        await self._conversation(conversation_id)
        q = (
            select(Message)
            .options(selectinload(Message.attachments))
            .where(Message.conversation_id == conversation_id)
        )
        if before is not None:
            q = q.where(Message.created_at < before)
        q = q.order_by(Message.created_at.desc()).limit(min(limit, 500))
        rows = list((await self.session.scalars(q)).all())
        rows.reverse()
        return rows

    async def add_user_message(self, conversation_id: uuid.UUID, data: MessageCreate) -> Message:
        conv, access = await self._conversation(conversation_id, Role.MEMBER)
        parsed = parse_message(data.content)
        msg = Message(
            conversation_id=conv.id,
            role="user",
            content=data.content,
            command=parsed.command,
            author_user_id=self._require_ctx().user_id,
        )
        self.session.add(msg)
        await self.session.flush()
        for asset_id in data.asset_ids:
            asset = await self.session.get(Asset, asset_id)
            if asset is None or asset.project_id != conv.project_id:
                raise NotFound(f"Asset {asset_id} not found in this project", code="asset_not_found")
            self.session.add(MessageAttachment(message_id=msg.id, asset_id=asset_id))
        for artifact_id in data.artifact_ids:
            artifact = await self.session.get(Artifact, artifact_id)
            if artifact is None or artifact.project_id != conv.project_id:
                raise NotFound(f"Artifact {artifact_id} not found in this project", code="artifact_not_found")
            self.session.add(MessageAttachment(message_id=msg.id, artifact_id=artifact_id))
        conv.last_message_at = datetime.now(UTC)
        if conv.title == "New chat":
            conv.title = (parsed.body or data.content).strip()[:80] or "New chat"
        await self.session.flush()
        return await self.session.scalar(
            select(Message)
            .options(selectinload(Message.attachments))
            .where(Message.id == msg.id)
            .execution_options(populate_existing=True)
        )  # type: ignore[return-value]

    async def add_assistant_message(
        self,
        conversation_id: uuid.UUID,
        *,
        content: str,
        agent: Agent | None,
        agent_version_id: uuid.UUID | None,
        run_id: uuid.UUID | None,
        artifact_ids: list[uuid.UUID],
        metadata: dict | None = None,
    ) -> Message:
        """Called by the run executor (no AuthContext checks: the run was already authorized)."""
        conv = await self.session.get(Conversation, conversation_id)
        if conv is None:
            raise NotFound("Conversation not found", code="conversation_not_found")
        msg = Message(
            conversation_id=conv.id,
            role="assistant",
            content=content,
            agent_id=agent.id if agent else None,
            agent_version_id=agent_version_id,
            run_id=run_id,
            metadata_json=metadata or {},
        )
        self.session.add(msg)
        await self.session.flush()
        for artifact_id in artifact_ids:
            self.session.add(MessageAttachment(message_id=msg.id, artifact_id=artifact_id))
        conv.last_message_at = datetime.now(UTC)
        await self.session.flush()
        return msg

    async def search(
        self, project_id: uuid.UUID, query: str, *, limit: int = 30
    ) -> list[tuple[Message, Conversation]]:
        await resolve_project(self.session, self._require_ctx(), project_id)
        q = (
            select(Message, Conversation)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .options(selectinload(Message.attachments))
            .where(
                Conversation.project_id == project_id,
                or_(Message.content.ilike(f"%{query}%"), Conversation.title.ilike(f"%{query}%")),
            )
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        return [(m, c) for m, c in (await self.session.execute(q)).all()]

    async def record_audit(self, action: str, conv: Conversation, access: ProjectAccess) -> None:
        await audit.record(
            self.session,
            action=action,
            entity_type="conversation",
            entity_id=conv.id,
            organization_id=access.workspace.organization_id,
            actor_user_id=self._require_ctx().user_id,
            request_id=self._require_ctx().request_id,
        )

    # ------------------------------------------------------------------ sticky agent + memory
    async def set_active_agent(
        self, conversation_id: uuid.UUID, *, command: str | None, agent_id: uuid.UUID | None
    ) -> Conversation:
        """`/copy` with no text: talk to the Copy Agent from now on. Neither → back to the Manager."""
        from app.domain.slash import normalize_command
        from app.models.agents import Agent

        conv, access = await self._conversation(conversation_id, Role.MEMBER)
        org_id = access.workspace.organization_id
        agent: Agent | None = None
        if agent_id is not None or (command and normalize_command(command) != "/auto"):
            q = select(Agent).where(
                Agent.organization_id == org_id,
                Agent.status == "active",
                Agent.active_version_id.is_not(None),
            )
            q = (
                q.where(Agent.id == agent_id)
                if agent_id is not None
                else q.where(Agent.command == normalize_command(command or ""))
            )
            agent = await self.session.scalar(q)
            if agent is None:
                raise ValidationFailed("No active agent handles that command", code="agent_unavailable")
            if agent.is_manager:
                agent = None
        conv.active_agent_id = agent.id if agent else None
        await self.session.flush()
        return conv

    async def clear_memory(self, conversation_id: uuid.UUID, agent_id: uuid.UUID | None = None) -> int:
        from sqlalchemy import delete

        from app.models.chat import AgentSession

        conv, _ = await self._conversation(conversation_id, Role.MEMBER)
        q = delete(AgentSession).where(AgentSession.conversation_id == conv.id)
        if agent_id is not None:
            q = q.where(AgentSession.agent_id == agent_id)
        result = await self.session.execute(q)
        return int(getattr(result, "rowcount", 0) or 0)


async def serialize_messages(session: AsyncSession, messages: list[Message]) -> list[MessageOut]:
    agent_ids = {m.agent_id for m in messages if m.agent_id}
    agents = (
        {a.id: a for a in (await session.scalars(select(Agent).where(Agent.id.in_(agent_ids)))).all()}
        if agent_ids
        else {}
    )
    asset_ids = {a.asset_id for m in messages for a in m.attachments if a.asset_id}
    artifact_ids = {a.artifact_id for m in messages for a in m.attachments if a.artifact_id}
    assets = (
        {a.id: a for a in (await session.scalars(select(Asset).where(Asset.id.in_(asset_ids)))).all()}
        if asset_ids
        else {}
    )
    artifacts = (
        {
            a.id: a
            for a in (await session.scalars(select(Artifact).where(Artifact.id.in_(artifact_ids)))).all()
        }
        if artifact_ids
        else {}
    )
    out: list[MessageOut] = []
    for m in messages:
        agent = agents.get(m.agent_id) if m.agent_id else None
        atts = []
        for a in m.attachments:
            if a.asset_id:
                asset = assets.get(a.asset_id)
                atts.append(
                    AttachmentOut(asset_id=a.asset_id, name=asset.name if asset else None, mime_type=None)
                )
            elif a.artifact_id:
                art = artifacts.get(a.artifact_id)
                atts.append(
                    AttachmentOut(artifact_id=a.artifact_id, name=art.name if art else None, mime_type=None)
                )
        out.append(
            from_orm(
                MessageOut,
                m,
                attachments=atts,
                agent_name=agent.name if agent else None,
                agent_command=agent.command if agent else None,
            )
        )
    return out


async def serialize_conversation(session: AsyncSession, conv: Conversation) -> ConversationOut:
    """ConversationOut with the sticky agent and per-agent memory sizes."""
    from app.models.agents import Agent
    from app.models.chat import AgentSession
    from app.schemas.chat import ActiveAgentOut, AgentMemoryOut

    active = await session.get(Agent, conv.active_agent_id) if conv.active_agent_id else None
    rows = (
        await session.execute(
            select(AgentSession, Agent)
            .join(Agent, Agent.id == AgentSession.agent_id)
            .where(AgentSession.conversation_id == conv.id)
            .order_by(AgentSession.updated_at.desc())
        )
    ).all()
    return from_orm(
        ConversationOut,
        conv,
        active_agent=ActiveAgentOut(id=active.id, name=active.name, slug=active.slug, command=active.command)
        if active
        else None,
        memory=[
            AgentMemoryOut(
                agent_id=a.id,
                agent_name=a.name,
                command=a.command,
                turns=s.turns,
                chars=s.chars,
                model=s.model,
                updated_at=s.updated_at,
            )
            for s, a in rows
        ],
    )
