from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from app.ports.runner import ProducedFile
from app.providers.base import ConnectionTest


@dataclass(slots=True)
class AgentConnection:
    """Everything the adapter needs; `api_key` is resolved server-side and never logged."""

    agent_slug: str
    agent_name: str
    connection_type: str
    endpoint: str | None
    api_key: str | None
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AgentFile:
    name: str
    mime_type: str
    content: bytes
    url: str | None = None  # signed URL when the agent API prefers references


@dataclass(slots=True)
class AgentReply:
    text: str
    session_id: str | None = None
    files: list[ProducedFile] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    status: int | None = None


OnDelta = Callable[[str], Awaitable[None]]


class AgentCallError(Exception):
    """Sanitized failure surfaced to the user ('Resize Agent could not complete the request')."""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


@runtime_checkable
class ExistingAgentProvider(Protocol):
    connection_type: str
    display_name: str
    supports_native_session: bool

    async def send_message(
        self,
        conn: AgentConnection,
        message: str,
        *,
        history: list[dict[str, str]],
        files: list[AgentFile],
        session_id: str | None,
        conversation_id: str,
        on_delta: OnDelta,
    ) -> AgentReply: ...

    async def test_connection(self, conn: AgentConnection) -> ConnectionTest: ...

    def validate_config(self, conn: AgentConnection) -> list[str]: ...
