"""Adapters for existing agents: OpenAI Responses (documented contract) and HTTP JSON endpoints."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from app.core.config import Settings
from app.providers.existing.base import AgentCallError, AgentConnection, AgentFile
from app.providers.existing.http_json import HttpJsonAgent
from app.providers.existing.openai_responses import OpenAIResponsesAgent


def _sse(events: list[dict[str, Any]]) -> bytes:
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events).encode()


async def _collect(deltas: list[str]):  # type: ignore[no-untyped-def]
    async def on_delta(d: str) -> None:
        deltas.append(d)

    return on_delta


async def test_openai_responses_streams_text_keeps_session_and_images() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content) if request.content else {}
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "gpt-5"}]})
        events = [
            {"type": "response.created", "response": {"id": "resp_1"}},
            {"type": "response.output_text.delta", "delta": "Hello "},
            {"type": "response.output_text.delta", "delta": "world"},
            {
                "type": "response.completed",
                "response": {
                    "id": "resp_1",
                    "usage": {
                        "input_tokens": 12,
                        "output_tokens": 3,
                        "input_tokens_details": {"cached_tokens": 4},
                    },
                    "output": [
                        {"type": "message", "content": [{"type": "output_text", "text": "Hello world"}]},
                        {"type": "image_generation_call", "result": "aGVsbG8="},
                    ],
                },
            },
        ]
        return httpx.Response(200, content=_sse(events), headers={"content-type": "text/event-stream"})

    provider = OpenAIResponsesAgent(transport=httpx.MockTransport(handler))
    conn = AgentConnection(
        "resize",
        "Resize Agent",
        "openai_responses",
        None,
        "sk-test-123456789",
        {"model": "gpt-5", "prompt_id": "pmpt_1"},
    )
    deltas: list[str] = []
    files = [
        AgentFile("poster.png", "image/png", b"\x89PNG"),
        AgentFile("brief.pdf", "application/pdf", b"%PDF"),
        AgentFile("x.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", b"zz"),
    ]
    reply = await provider.send_message(
        conn,
        "resize to 4:5",
        history=[{"role": "user", "content": "earlier"}],
        files=files,
        session_id=None,
        conversation_id="c1",
        on_delta=await _collect(deltas),
    )
    assert reply.text == "Hello world" and deltas == ["Hello ", "world"] and reply.session_id == "resp_1"
    assert reply.usage["input_tokens"] == 12 and reply.usage["cached_input_tokens"] == 4
    assert (
        len(reply.files) == 1
        and reply.files[0].mime_type == "image/png"
        and reply.files[0].content == b"hello"
    )
    body = seen["body"]
    assert seen["url"].endswith("/v1/responses") and seen["auth"] == "Bearer sk-test-123456789"
    assert body["model"] == "gpt-5" and body["prompt"] == {"id": "pmpt_1"} and body["stream"] is True
    assert "instructions" not in body  # no Origin system prompt is injected
    assert (
        body["input"][0]["role"] == "user" and body["input"][0]["content"][0]["text"] == "earlier"
    )  # Origin-kept history
    last = body["input"][-1]["content"]
    assert last[0] == {"type": "input_text", "text": "resize to 4:5"}
    assert last[1]["type"] == "input_image" and last[1]["image_url"].startswith("data:image/png;base64,")
    assert last[2]["type"] == "input_file" and last[2]["filename"] == "brief.pdf"
    assert any("docx" in w for w in reply.usage["warnings"])

    # follow-up with a native session: previous_response_id, no history replay
    reply2 = await provider.send_message(
        conn,
        "smaller heading",
        history=[{"role": "user", "content": "x"}],
        files=[],
        session_id="resp_1",
        conversation_id="c1",
        on_delta=await _collect([]),
    )
    assert (
        seen["body"]["previous_response_id"] == "resp_1"
        and len(seen["body"]["input"]) == 1
        and reply2.session_id == "resp_1"
    )
    test = await provider.test_connection(conn)
    assert test.ok and "gpt-5" in test.message


async def test_openai_responses_errors_are_sanitized() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "Incorrect API key provided: sk-test-1234"}})

    provider = OpenAIResponsesAgent(transport=httpx.MockTransport(handler))
    conn = AgentConnection("qc", "QC Agent", "openai_responses", None, "sk-bad-000000000", {"model": "gpt-5"})
    with pytest.raises(AgentCallError) as exc:
        await provider.send_message(
            conn,
            "hi",
            history=[],
            files=[],
            session_id=None,
            conversation_id="c",
            on_delta=await _collect([]),
        )
    assert exc.value.code == "agent_auth" and "sk-test" not in exc.value.message
    assert (
        await provider.test_connection(AgentConnection("qc", "QC", "openai_responses", None, None, {}))
    ).ok is False


async def test_http_json_agent_maps_request_and_response(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.core.ssrf as ssrf

    monkeypatch.setattr(ssrf, "resolve_host", lambda host: ["93.184.216.34"])
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["headers"] = dict(request.headers)
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "data": {"answer": "Resized!", "thread": "t-9"},
                "files": [{"name": "out.png", "mime_type": "image/png", "data": "aGVsbG8="}],
            },
        )

    settings = Settings(_env_file=None)
    provider = HttpJsonAgent(settings, transport=httpx.MockTransport(handler))
    conn = AgentConnection(
        "resize",
        "Resize Agent",
        "http",
        "https://agents.example.com/resize",
        "key-abcdef123456",
        {
            "response_text_path": "data.answer",
            "session_id_path": "data.thread",
            "api_key_header": "X-Api-Key",
        },
    )
    deltas: list[str] = []
    reply = await provider.send_message(
        conn,
        "resize it",
        history=[{"role": "user", "content": "hi"}],
        files=[AgentFile("a.png", "image/png", b"x", url="https://cdn.example.com/a.png")],
        session_id="t-8",
        conversation_id="conv",
        on_delta=await _collect(deltas),
    )
    assert reply.text == "Resized!" and reply.session_id == "t-9" and deltas == ["Resized!"]
    assert reply.files[0].filename == "out.png" and reply.files[0].content == b"hello"
    assert seen["headers"]["x-api-key"] == "key-abcdef123456" and "authorization" not in seen["headers"]
    assert seen["body"] == {
        "message": "resize it",
        "session_id": "t-8",
        "conversation_id": "conv",
        "history": [{"role": "user", "content": "hi"}],
        "files": [
            {"name": "a.png", "mime_type": "image/png", "size": 1, "url": "https://cdn.example.com/a.png"}
        ],
    }
    blocked = AgentConnection("x", "X", "http", "https://169.254.169.254/agent", None, {})
    with pytest.raises(AgentCallError) as exc:
        await provider.send_message(
            blocked,
            "hi",
            history=[],
            files=[],
            session_id=None,
            conversation_id="c",
            on_delta=await _collect([]),
        )
    assert exc.value.code == "agent_not_configured"
    assert (await provider.test_connection(conn)).ok
