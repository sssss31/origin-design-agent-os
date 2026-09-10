"""Execution event vocabulary (spec §9) and the safe payload whitelist (spec §9 'what to show').

`SafeEventPayload` uses `extra="forbid"`: anything not listed here (for example model
reasoning or raw provider payloads) is rejected at construction time, so it cannot reach
the database, the SSE stream or the browser.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EventType(StrEnum):
    RUN_STARTED = "run.started"
    NODE_STARTED = "node.started"
    CONTEXT_LOADED = "context.loaded"
    AGENT_STARTED = "agent.started"
    TOOL_STARTED = "tool.started"
    TOOL_COMPLETED = "tool.completed"
    ARTIFACT_CREATED = "artifact.created"
    CLARIFICATION_REQUESTED = "clarification.requested"
    CLARIFICATION_RECEIVED = "clarification.received"
    NODE_COMPLETED = "node.completed"
    NODE_FAILED = "node.failed"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    RUN_CANCELLED = "run.cancelled"
    HEARTBEAT = "heartbeat"


class SafeEventPayload(BaseModel):
    """Whitelisted fields that may be shown to the user."""

    model_config = ConfigDict(extra="forbid")

    node_id: str | None = None
    node_name: str | None = None
    node_index: int | None = None
    node_status: str | None = None
    run_status: str | None = None
    agent_slug: str | None = None
    agent_name: str | None = None
    agent_version: int | None = None
    tool_slug: str | None = None
    tool_display_name: str | None = None
    input_summary: str | None = Field(default=None, max_length=2000)
    output_summary: str | None = Field(default=None, max_length=4000)
    artifact_id: str | None = None
    artifact_type: str | None = None
    artifact_version: int | None = None
    question: str | None = Field(default=None, max_length=2000)
    question_schema: dict[str, Any] | None = None
    defaults_used: list[str] | None = None
    context_sources: list[str] | None = None
    error_code: str | None = None
    error_message: str | None = Field(default=None, max_length=2000)
    retryable: bool | None = None
    duration_ms: int | None = None
    findings_count: int | None = None
    qc_passed: bool | None = None


class ExecutionEvent(BaseModel):
    """Wire format for one event (DB row and SSE `data:`)."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    sequence_no: int
    type: EventType
    occurred_at: str
    node_run_id: str | None = None
    payload: SafeEventPayload = Field(default_factory=SafeEventPayload)


def build_payload(**fields: Any) -> SafeEventPayload:
    """Construct a payload, raising if an unknown (potentially unsafe) field is supplied."""
    return SafeEventPayload(**fields)
