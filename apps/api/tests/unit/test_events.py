import pytest
from app.domain.events import EventType, ExecutionEvent, SafeEventPayload, build_payload
from pydantic import ValidationError


def test_payload_whitelist_rejects_reasoning_fields() -> None:
    with pytest.raises(ValidationError):
        build_payload(node_name="Resize", reasoning="secret chain of thought")
    with pytest.raises(ValidationError):
        SafeEventPayload(raw_provider_response={"choices": []})


def test_payload_accepts_operational_fields() -> None:
    p = build_payload(node_name="Resize", agent_slug="resize", tool_slug="image.resize", duration_ms=12)
    assert p.model_dump(exclude_none=True) == {
        "node_name": "Resize",
        "agent_slug": "resize",
        "tool_slug": "image.resize",
        "duration_ms": 12,
    }


def test_event_vocabulary_matches_spec() -> None:
    spec_events = {
        "run.started",
        "node.started",
        "context.loaded",
        "agent.started",
        "tool.started",
        "tool.completed",
        "artifact.created",
        "clarification.requested",
        "clarification.received",
        "node.completed",
        "node.failed",
        "run.completed",
        "run.failed",
    }
    assert spec_events.issubset({e.value for e in EventType})


def test_event_wire_format() -> None:
    ev = ExecutionEvent(
        run_id="run_1", sequence_no=1, type=EventType.RUN_STARTED, occurred_at="2026-09-10T00:00:00Z"
    )
    assert ev.model_dump()["payload"] == SafeEventPayload().model_dump()
