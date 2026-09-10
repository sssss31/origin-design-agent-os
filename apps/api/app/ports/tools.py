"""ToolExecutor port (spec §12 tool execution contract)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable


class ExecutorType(StrEnum):
    INTERNAL_FUNCTION = "internal_function"
    HTTP_API = "http_api"
    MCP = "mcp"
    SANDBOX = "sandbox"


@dataclass(slots=True)
class ToolSpec:
    slug: str
    display_name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None = None
    executor_type: ExecutorType = ExecutorType.INTERNAL_FUNCTION
    timeout_seconds: int = 60
    requires_secret: str | None = None
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ToolCall:
    tool: ToolSpec
    arguments: dict[str, Any]
    run_id: str | None = None
    node_run_id: str | None = None


@dataclass(slots=True)
class ToolResult:
    ok: bool
    output: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    duration_ms: int = 0
    files: list[Any] = field(default_factory=list)


ToolFunction = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


@runtime_checkable
class ToolExecutor(Protocol):
    executor_type: ExecutorType

    async def execute(self, call: ToolCall) -> ToolResult: ...
