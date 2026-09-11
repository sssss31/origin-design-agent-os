"""Execution context handed to built-in tools (never serialized, never logged)."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ports.storage import ObjectStorage


@dataclass(slots=True)
class ToolContext:
    session_factory: async_sessionmaker[AsyncSession]
    storage: ObjectStorage
    organization_id: uuid.UUID
    workspace_id: uuid.UUID
    project_id: uuid.UUID
    conversation_id: uuid.UUID | None
    run_id: uuid.UUID | None
    node_run_id: uuid.UUID | None
    agent_version_id: uuid.UUID | None
    created_by: uuid.UUID | None
    provider_credentials: dict[str, str] = field(default_factory=dict, repr=False)
    settings: dict[str, Any] = field(default_factory=dict)


ToolFn = Callable[[dict[str, Any], ToolContext], Awaitable[dict[str, Any]]]
