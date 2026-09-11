from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class RunCreate(BaseModel):
    """Spec §11 run creation request. Either reference an existing message or send content."""

    message_id: uuid.UUID | None = None
    content: str | None = Field(default=None, min_length=1, max_length=50000)
    command: str | None = Field(default=None, max_length=41)
    selected_asset_ids: list[uuid.UUID] = Field(default_factory=list)
    selected_artifact_ids: list[uuid.UUID] = Field(default_factory=list)
    preferred_agent_id: uuid.UUID | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class RunCreated(BaseModel):
    run_id: uuid.UUID
    status: str
    event_stream_url: str
    message_id: uuid.UUID | None


class NodeRunOut(ORMModel):
    id: uuid.UUID
    node_id: str
    index: int
    name: str
    kind: str
    status: str
    agent_id: uuid.UUID | None
    agent_version_id: uuid.UUID | None
    output_json: dict[str, Any]
    error_json: dict[str, Any] | None
    question: str | None
    question_schema: dict[str, Any] | None
    answer: str | None
    attempt: int
    started_at: datetime | None
    finished_at: datetime | None


class RunOut(ORMModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    project_id: uuid.UUID
    message_id: uuid.UUID | None
    status: str
    command: str | None
    user_input: str
    entry_agent_id: uuid.UUID | None
    result_json: dict[str, Any]
    error_json: dict[str, Any] | None
    cancel_requested: bool
    attempt: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    nodes: list[NodeRunOut] = Field(default_factory=list)
    event_stream_url: str = ""


class ClarificationAnswer(BaseModel):
    answer: str = Field(min_length=1, max_length=10000)
    data: dict[str, Any] = Field(default_factory=dict)


class EventOut(BaseModel):
    run_id: str
    sequence_no: int
    type: str
    occurred_at: str
    node_run_id: str | None
    payload: dict[str, Any]
