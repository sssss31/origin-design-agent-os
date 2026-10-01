"""GPT-style image generation through an OpenAI Responses agent: partial renders are streamed as
`artifact.preview` events (signed, downloadable), the finished image is a real artifact on the reply."""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx
from app.domain.roles import Role

from tests.api.test_runs import drain, png_bytes, setup_org
from tests.conftest import requires_db

pytestmark = requires_db
ADMIN = "/api/v1/admin"


def _sse(events: list[dict[str, Any]]) -> bytes:
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events).encode()


def _openai_transport(calls: list[dict[str, Any]]) -> httpx.MockTransport:
    final_b64 = base64.b64encode(png_bytes()).decode()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "gpt-5"}]})
        body = json.loads(request.content)
        calls.append(body)
        events = [
            {"type": "response.created", "response": {"id": "resp_img"}},
            {"type": "response.image_generation_call.generating", "item_id": "ig_1"},
            {
                "type": "response.image_generation_call.partial_image",
                "item_id": "ig_1",
                "partial_image_index": 0,
                "partial_image_b64": final_b64,
            },
            {
                "type": "response.image_generation_call.partial_image",
                "item_id": "ig_1",
                "partial_image_index": 1,
                "partial_image_b64": final_b64,
            },
            {"type": "response.output_text.delta", "delta": "Here is your 4:5 poster."},
            {
                "type": "response.completed",
                "response": {
                    "id": "resp_img",
                    "usage": {"input_tokens": 5, "output_tokens": 5},
                    "output": [
                        {
                            "type": "image_generation_call",
                            "id": "ig_1",
                            "result": final_b64,
                            "output_format": "png",
                        },
                        {
                            "type": "message",
                            "content": [{"type": "output_text", "text": "Here is your 4:5 poster."}],
                        },
                    ],
                },
            },
        ]
        return httpx.Response(200, content=_sse(events), headers={"content-type": "text/event-stream"})

    return httpx.MockTransport(handler)


async def test_partial_images_stream_and_final_image_is_an_artifact(app, client, make_user) -> None:  # type: ignore[no-untyped-def]
    admin = await make_user("admin@example.com", role=Role.ADMIN)
    _provider, _ws, project = await setup_org(admin)
    seed = await admin.post(f"{ADMIN}/seed/agent-registry", json={"connection_type": "http"})
    assert seed.status_code == 200
    agents = {a["command"]: a for a in (await admin.get(f"{ADMIN}/agents")).json()}
    res = await admin.put(
        f"{ADMIN}/agents/{agents['/resize']['id']}/connection",
        json={
            "connection_type": "openai_responses",
            "api_endpoint": "https://api.openai.com/v1",
            "api_key": "sk-test-abcdefghijklmnop",
            "config": {"model": "gpt-5"},
        },
    )
    assert res.status_code == 200, res.text
    calls: list[dict[str, Any]] = []
    app.state.adapters.http_transport = _openai_transport(calls)
    try:
        conv = (
            await admin.post(f"/api/v1/projects/{project['id']}/conversations", json={"title": "Poster"})
        ).json()
        up = await admin.client.post(
            f"/api/v1/projects/{project['id']}/assets",
            headers=admin.headers,
            files={"file": ("poster.png", png_bytes(), "image/png")},
            data={"kind": "image"},
        )
        created = (
            await admin.post(
                f"/api/v1/conversations/{conv['id']}/runs",
                json={"content": "/resize make it 4:5", "selected_asset_ids": [up.json()["id"]]},
            )
        ).json()
        await drain(app)
        run = (await admin.get(f"/api/v1/runs/{created['run_id']}")).json()
        assert run["status"] == "SUCCEEDED", run["error_json"]
        # the request carried the attached image and the image tool with partial renders
        body = calls[-1]
        assert body["input"][-1]["content"][1]["type"] == "input_image"
        assert {"type": "image_generation", "partial_images": 2} in body["tools"]

        history = (await admin.get(f"/api/v1/runs/{created['run_id']}/events/history")).json()
        previews = [e for e in history if e["type"] == "artifact.preview"]
        assert [p["payload"]["artifact_version"] for p in previews] == [0, 1]
        assert all(p["payload"]["artifact_id"] == "ig_1" and p["payload"]["preview_url"] for p in previews)
        # the preview URL is a signed download that serves the partial render
        url = previews[-1]["payload"]["preview_url"]
        path = url.split("//", 1)[-1].split("/", 1)[1]
        img = await client.get("/" + path)
        assert img.status_code == 200 and img.headers["content-type"].startswith("image/png")
        # status line reached the stream, the final image is an artifact on the saved reply
        streamed = "".join(
            e["payload"].get("delta") or "" for e in history if e["type"] == "response.streaming"
        )
        assert "Generating image…" in streamed and "Here is your 4:5 poster." in streamed
        assert [e["payload"]["artifact_type"] for e in history if e["type"] == "artifact.created"] == [
            "image"
        ]
        messages = (await admin.get(f"/api/v1/conversations/{conv['id']}/messages")).json()
        reply = messages[-1]
        assert reply["role"] == "assistant" and reply["content"] == "Here is your 4:5 poster."
        assert len(reply["attachments"]) == 1 and reply["attachments"][0]["mime_type"] == "image/png"
        # the user's own attachment is reported with its image type so the UI can render a thumbnail
        user_msg = next(m for m in messages if m["role"] == "user")
        assert (
            user_msg["attachments"][0]["asset_id"] and user_msg["attachments"][0]["mime_type"] == "image/png"
        )
    finally:
        app.state.adapters.http_transport = None
