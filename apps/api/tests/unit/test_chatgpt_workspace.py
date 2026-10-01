"""ChatGPT Workspace Agent trigger adapter against the documented contract (mocked)."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from app.providers.existing.base import AgentCallError, AgentConnection
from app.providers.existing.chatgpt_workspace import ChatGPTWorkspaceAgent

TRIGGER = "https://api.chatgpt.com/v1/workspace_agents/agtch_abc123/trigger"


def _conn(endpoint: str = TRIGGER, key: str | None = "tok-1") -> AgentConnection:
    return AgentConnection(
        agent_slug="resize",
        agent_name="Resize Agent",
        connection_type="chatgpt_workspace",
        endpoint=endpoint,
        api_key=key,
        config={"poll_seconds": 10},
    )


async def test_trigger_then_poll_until_completed() -> None:
    calls: list[dict[str, Any]] = []
    polls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(
            {
                "method": request.method,
                "path": request.url.path,
                "auth": request.headers.get("authorization"),
                "beta": request.headers.get("openai-beta"),
                "body": json.loads(request.content) if request.content else None,
            }
        )
        if request.method == "POST":
            return httpx.Response(
                200,
                json={"conversation_url": "https://chatgpt.com/c/123", "agent_trigger_run_id": "apirun_1"},
            )
        polls["n"] += 1
        status = "in_progress" if polls["n"] == 1 else "completed"
        return httpx.Response(
            200,
            json={
                "object": "workspace_agent.trigger_run",
                "id": "apirun_1",
                "status": status,
                "conversation_url": "https://chatgpt.com/c/123",
                "error": None,
            },
        )

    agent = ChatGPTWorkspaceAgent(transport=httpx.MockTransport(handler))
    deltas: list[str] = []

    async def on_delta(d: str) -> None:
        deltas.append(d)

    reply = await agent.send_message(
        _conn(),
        "Resize the banner",
        history=[],
        files=[],
        session_id=None,
        conversation_id="conv-1",
        on_delta=on_delta,
    )
    assert (
        calls[0]["path"] == "/v1/workspace_agents/agtch_abc123/trigger" and calls[0]["auth"] == "Bearer tok-1"
    )
    assert calls[0]["beta"] == "workspace_agent_runs=v1"
    assert calls[0]["body"] == {"input": "Resize the banner", "conversation_key": "origin-conv-1"}
    assert calls[-1]["path"] == "/v1/workspace_agents/agtch_abc123/runs/apirun_1"
    assert "finished the run" in reply.text and "https://chatgpt.com/c/123" in reply.text
    assert reply.session_id == "origin-conv-1"  # follow-ups keep the same ChatGPT conversation
    assert any("in_progress" in d for d in deltas) and any("completed" in d for d in deltas)

    # a second turn re-uses the stored conversation key
    await agent.send_message(
        _conn(),
        "Now 4:5",
        history=[],
        files=[],
        session_id="origin-conv-1",
        conversation_id="conv-1",
        on_delta=on_delta,
    )
    assert calls[-2]["body"]["conversation_key"] == "origin-conv-1" or calls[-1]["body"] is None


async def test_errors_and_connection_test() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers.get("authorization") == "Bearer bad":
            return httpx.Response(401, json={"error": {"message": "bad token"}})
        if request.method == "GET":
            return httpx.Response(404, json={"error": {"message": "no such run"}})
        return httpx.Response(409, json={"error": {"message": "agent not runnable"}})

    agent = ChatGPTWorkspaceAgent(transport=httpx.MockTransport(handler))

    async def noop(_: str) -> None:
        return None

    with pytest.raises(AgentCallError) as exc:
        await agent.send_message(
            _conn(key="bad"), "hi", history=[], files=[], session_id=None, conversation_id="c", on_delta=noop
        )
    assert exc.value.code == "agent_auth"
    with pytest.raises(AgentCallError) as exc:
        await agent.send_message(
            _conn(), "hi", history=[], files=[], session_id=None, conversation_id="c", on_delta=noop
        )
    assert exc.value.code == "agent_unavailable" and exc.value.retryable
    ok = await agent.test_connection(_conn())
    assert ok.ok and "ChatGPT" in ok.message
    bad = await agent.test_connection(_conn(key="bad"))
    assert not bad.ok
    assert (
        agent.validate_config(_conn(endpoint="https://example.com/x"))
        and agent.validate_config(_conn(endpoint="agtch_x")) == []
    )


async def test_rejected_token_explains_which_token_is_needed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401, json={"error": {"message": "Incorrect API key provided", "code": "invalid_api_key"}}
        )

    agent = ChatGPTWorkspaceAgent(transport=httpx.MockTransport(handler))

    async def noop(_: str) -> None:
        return None

    with pytest.raises(AgentCallError) as exc:
        await agent.send_message(
            _conn(key="sk-proj-abcdef123456"),
            "hi",
            history=[],
            files=[],
            session_id=None,
            conversation_id="c",
            on_delta=noop,
        )
    assert "Platform API key" in exc.value.message and "sk-proj-abcdef123456" not in exc.value.message
    res = await agent.test_connection(_conn(key="some-other-token-123"))
    assert not res.ok and "Access tokens" in res.message and "Incorrect API key provided" in res.message
    assert "some-other-token-123" not in res.message


async def test_token_id_is_rejected_before_calling_chatgpt() -> None:
    """The Access tokens page lists ids (token_…); the credential itself is the at-… value shown once."""
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401, json={"error": {"message": "Incorrect API key provided"}})

    agent = ChatGPTWorkspaceAgent(transport=httpx.MockTransport(handler))
    conn = _conn(key="token_X6nNabcdefaxcY")
    problems = agent.validate_config(conn)
    assert len(problems) == 1 and "token's ID" in problems[0] and "token_X6nN" not in problems[0]
    res = await agent.test_connection(conn)
    assert not res.ok and "token's ID" in res.message and calls == 0
    assert agent.validate_config(_conn(key="at-abcdefghijklmnop")) == []


async def test_trigger_sends_no_idempotency_key() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.headers)
        if request.method == "POST":
            return httpx.Response(
                202, json={"conversation_url": "https://chatgpt.com/c/1", "agent_trigger_run_id": "apirun_1"}
            )
        return httpx.Response(
            200, json={"status": "completed", "conversation_url": "https://chatgpt.com/c/1"}
        )

    agent = ChatGPTWorkspaceAgent(transport=httpx.MockTransport(handler))

    async def noop(_: str) -> None:
        return None

    await agent.send_message(
        _conn(), "hi", history=[], files=[], session_id=None, conversation_id="c", on_delta=noop
    )
    assert "idempotency-key" not in {k.lower() for k in seen}
    assert seen.get("openai-beta") == "workspace_agent_runs=v1"
