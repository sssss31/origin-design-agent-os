from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class ConversationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    status: str | None = Field(default=None, pattern="^(active|archived)$")


class ConversationOut(ORMModel):
    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    status: str
    last_message_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AttachmentOut(BaseModel):
    asset_id: uuid.UUID | None = None
    artifact_id: uuid.UUID | None = None
    name: str | None = None
    mime_type: str | None = None


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=50000)
    asset_ids: list[uuid.UUID] = Field(default_factory=list)
    artifact_ids: list[uuid.UUID] = Field(default_factory=list)


class MessageOut(ORMModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    command: str | None
    agent_id: uuid.UUID | None
    agent_version_id: uuid.UUID | None
    run_id: uuid.UUID | None
    author_user_id: uuid.UUID | None
    metadata_json: dict[str, Any]
    created_at: datetime
    attachments: list[AttachmentOut] = Field(default_factory=list)
    agent_name: str | None = None
    agent_command: str | None = None


class MessageSearchHit(BaseModel):
    message: MessageOut
    conversation_title: str
