"""My Work (Workspace V0 §20–§22): every conversation with agents used, files, outputs; search."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dashboard import accessible_project_ids
from app.core.authz import DB, Auth, AuthContext
from app.core.errors import NotFound
from app.models.agents import Agent
from app.models.chat import Conversation, Message, MessageAttachment
from app.models.files import Artifact, Asset

router = APIRouter(prefix="/work", tags=["work"])


class WorkItem(BaseModel):
    conversation_id: uuid.UUID
    title: str
    project_id: uuid.UUID
    project_name: str
    status: str
    created_at: datetime
    last_message_at: datetime | None
    agents_used: list[dict] = Field(default_factory=list)
    primary_agent: str | None = None
    messages: int = 0
    files: int = 0
    outputs: int = 0


async def _items(
    session: AsyncSession,
    ctx: AuthContext,
    *,
    search: str | None,
    agent_id: uuid.UUID | None,
    date_from: datetime | None,
    date_to: datetime | None,
    limit: int,
    conversation_id: uuid.UUID | None = None,
) -> list[WorkItem]:
    projects = await accessible_project_ids(session, ctx)
    if not projects:
        return []
    q = select(Conversation).where(Conversation.project_id.in_(projects.keys()))
    if conversation_id is not None:
        q = q.where(Conversation.id == conversation_id)
    if date_from is not None:
        q = q.where(Conversation.created_at >= date_from)
    if date_to is not None:
        q = q.where(Conversation.created_at <= date_to)
    if search:
        like = f"%{search.strip()}%"
        msg_hits = select(Message.conversation_id).where(Message.content.ilike(like))
        file_hits = (
            select(MessageAttachment.message_id)
            .join(Asset, Asset.id == MessageAttachment.asset_id)
            .where(Asset.name.ilike(like))
        )
        file_conv = select(Message.conversation_id).where(Message.id.in_(file_hits))
        agent_conv = (
            select(Message.conversation_id)
            .join(Agent, Agent.id == Message.agent_id)
            .where(or_(Agent.name.ilike(like), Agent.command.ilike(like)))
        )
        q = q.where(
            or_(
                Conversation.title.ilike(like),
                Conversation.id.in_(msg_hits),
                Conversation.id.in_(file_conv),
                Conversation.id.in_(agent_conv),
            )
        )
    if agent_id is not None:
        q = q.where(Conversation.id.in_(select(Message.conversation_id).where(Message.agent_id == agent_id)))
    q = q.order_by(func.coalesce(Conversation.last_message_at, Conversation.created_at).desc()).limit(limit)
    convs = list((await session.scalars(q)).all())
    if not convs:
        return []
    ids = [c.id for c in convs]
    msg_counts: dict[uuid.UUID, int] = {
        row[0]: int(row[1])
        for row in (
            await session.execute(
                select(Message.conversation_id, func.count(Message.id))
                .where(Message.conversation_id.in_(ids))
                .group_by(Message.conversation_id)
            )
        ).all()
    }
    file_counts: dict[uuid.UUID, int] = {
        row[0]: int(row[1])
        for row in (
            await session.execute(
                select(Message.conversation_id, func.count(func.distinct(MessageAttachment.asset_id)))
                .join(MessageAttachment, MessageAttachment.message_id == Message.id)
                .where(Message.conversation_id.in_(ids), MessageAttachment.asset_id.is_not(None))
                .group_by(Message.conversation_id)
            )
        ).all()
    }
    output_counts: dict[uuid.UUID | None, int] = {
        row[0]: int(row[1])
        for row in (
            await session.execute(
                select(Artifact.conversation_id, func.count(Artifact.id))
                .where(Artifact.conversation_id.in_(ids))
                .group_by(Artifact.conversation_id)
            )
        ).all()
    }
    agent_rows = (
        await session.execute(
            select(
                Message.conversation_id,
                Agent.id,
                Agent.name,
                Agent.command,
                func.count(Message.id),
                func.max(Message.created_at),
            )
            .join(Agent, Agent.id == Message.agent_id)
            .where(Message.conversation_id.in_(ids))
            .group_by(Message.conversation_id, Agent.id, Agent.name, Agent.command)
        )
    ).all()
    agents_by_conv: dict[uuid.UUID, list[dict]] = {}
    for conv_id, aid, name, command, count, last in agent_rows:
        agents_by_conv.setdefault(conv_id, []).append(
            {
                "id": str(aid),
                "name": name,
                "command": command,
                "messages": int(count),
                "last_used": last.isoformat() if last else None,
            }
        )
    out: list[WorkItem] = []
    for c in convs:
        agents = sorted(agents_by_conv.get(c.id, []), key=lambda a: a["last_used"] or "", reverse=True)
        out.append(
            WorkItem(
                conversation_id=c.id,
                title=c.title,
                project_id=c.project_id,
                project_name=projects[c.project_id][0].name,
                status=c.status,
                created_at=c.created_at,
                last_message_at=c.last_message_at,
                agents_used=agents,
                primary_agent=max(agents, key=lambda a: a["messages"])["name"] if agents else None,
                messages=int(msg_counts.get(c.id, 0)),
                files=int(file_counts.get(c.id, 0)),
                outputs=int(output_counts.get(c.id, 0)),
            )
        )
    return out


@router.get("", response_model=list[WorkItem])
async def my_work(
    ctx: Auth,
    session: DB,
    search: str | None = Query(default=None, max_length=200),
    agent_id: uuid.UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[WorkItem]:
    return await _items(
        session, ctx, search=search, agent_id=agent_id, date_from=date_from, date_to=date_to, limit=limit
    )


@router.get("/{conversation_id}", response_model=WorkItem)
async def work_item(conversation_id: uuid.UUID, ctx: Auth, session: DB) -> WorkItem:
    items = await _items(
        session,
        ctx,
        search=None,
        agent_id=None,
        date_from=None,
        date_to=None,
        limit=1,
        conversation_id=conversation_id,
    )
    if not items:
        raise NotFound("Conversation not found", code="conversation_not_found")
    return items[0]
