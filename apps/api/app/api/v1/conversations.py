from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Query, status

from app.core.authz import DB, Auth
from app.schemas.chat import (
    ConversationCreate,
    ConversationOut,
    ConversationUpdate,
    MessageCreate,
    MessageOut,
    MessageSearchHit,
)
from app.schemas.common import from_orm
from app.services.conversations import ConversationService, serialize_messages

router = APIRouter(tags=["chat"])


@router.get("/projects/{project_id}/conversations", response_model=list[ConversationOut])
async def list_conversations(
    project_id: uuid.UUID,
    ctx: Auth,
    session: DB,
    include_archived: bool = False,
    search: str | None = Query(default=None, max_length=200),
) -> list[ConversationOut]:
    rows = await ConversationService(session, ctx).list_for_project(
        project_id, include_archived=include_archived, search=search
    )
    return [from_orm(ConversationOut, c) for c in rows]


@router.post(
    "/projects/{project_id}/conversations",
    response_model=ConversationOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    project_id: uuid.UUID, body: ConversationCreate, ctx: Auth, session: DB
) -> ConversationOut:
    return from_orm(ConversationOut, await ConversationService(session, ctx).create(project_id, body))


@router.get("/projects/{project_id}/messages/search", response_model=list[MessageSearchHit])
async def search_messages(
    project_id: uuid.UUID, ctx: Auth, session: DB, q: str = Query(min_length=1, max_length=200)
) -> list[MessageSearchHit]:
    hits = await ConversationService(session, ctx).search(project_id, q)
    serialized = await serialize_messages(session, [m for m, _ in hits])
    return [
        MessageSearchHit(message=m, conversation_title=c.title)
        for m, (_, c) in zip(serialized, hits, strict=True)
    ]


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
async def get_conversation(conversation_id: uuid.UUID, ctx: Auth, session: DB) -> ConversationOut:
    conv, _ = await ConversationService(session, ctx).get(conversation_id)
    return from_orm(ConversationOut, conv)


@router.patch("/conversations/{conversation_id}", response_model=ConversationOut)
async def update_conversation(
    conversation_id: uuid.UUID, body: ConversationUpdate, ctx: Auth, session: DB
) -> ConversationOut:
    return from_orm(ConversationOut, await ConversationService(session, ctx).update(conversation_id, body))


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
async def list_messages(
    conversation_id: uuid.UUID,
    ctx: Auth,
    session: DB,
    limit: int = Query(default=200, ge=1, le=500),
    before: datetime | None = None,
) -> list[MessageOut]:
    rows = await ConversationService(session, ctx).messages(conversation_id, limit=limit, before=before)
    return await serialize_messages(session, rows)


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
)
async def post_message(conversation_id: uuid.UUID, body: MessageCreate, ctx: Auth, session: DB) -> MessageOut:
    msg = await ConversationService(session, ctx).add_user_message(conversation_id, body)
    return (await serialize_messages(session, [msg]))[0]
