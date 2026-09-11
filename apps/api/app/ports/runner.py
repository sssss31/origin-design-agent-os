"""AgentRunner port (spec §12): the boundary between our runtime and any LLM SDK."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(slots=True)
class RuntimeTool:
    slug: str
    display_name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None = None


@dataclass(slots=True)
class RuntimeAgent:
    """A fully-resolved, immutable snapshot of an agent version + composed instructions."""

    slug: str
    name: str
    version: int
    instructions: str
    model: str
    provider_type: str
    model_settings: dict[str, Any] = field(default_factory=dict)
    tools: list[RuntimeTool] = field(default_factory=list)
    output_schema: dict[str, Any] | None = None
    can_ask_clarification: bool = True
    max_steps: int = 20
    timeout_seconds: int = 300
    provider_credentials: dict[str, str] = field(default_factory=dict, repr=False)


@dataclass(slots=True)
class RunInput:
    user_input: str
    context_summary: str = ""
    resume_state: dict[str, Any] | None = None
    clarification_answer: str | None = None
    attachments: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class ProducedFile:
    filename: str
    content: bytes
    mime_type: str
    artifact_type: str = "image"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RunOutcome:
    output_text: str
    structured_output: dict[str, Any] | None = None
    requires_clarification: bool = False
    question: str | None = None
    question_schema: dict[str, Any] | None = None
    resume_state: dict[str, Any] | None = None
    files: list[ProducedFile] = field(default_factory=list)
    defaults_used: list[str] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    steps: int = 0


ToolInvoker = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]
EventEmitter = Callable[[str, dict[str, Any]], Awaitable[None]]


@runtime_checkable
class AgentRunner(Protocol):
    name: str

    async def run(
        self,
        agent: RuntimeAgent,
        run_input: RunInput,
        *,
        invoke_tool: ToolInvoker,
        emit: EventEmitter,
    ) -> RunOutcome: ...
