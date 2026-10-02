"""Execution architecture brief: a ChatGPT Workspace agent answers *inside* Origin once its native runtime
is configured (execution_mode = origin_native); in workspace_trigger mode the result is external."""

from __future__ import annotations

from typing import Any

import httpx
from app.domain.roles import Role

from tests.api.test_image_previews import _openai_transport
from tests.api.test_runs import drain, png_bytes, setup_org
from tests.conftest import requires_db

pytestmark = requires_db
ADMIN = "/api/v1/admin"
TRIGGER = "https://api.chatgpt.com/v1/workspace_agents/agtch_abc123/trigger"


def _mixed_transport(openai_calls: list[dict[str, Any]], chatgpt_calls: list[str]) -> httpx.MockTransport:
    openai = _openai_transport(openai_calls)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.chatgpt.com":
            chatgpt_calls.append(request.url.path)
            if request.method == "POST":
                return httpx.Response(
                    202,
                    json={
                        "conversation_url": "https://chatgpt.com/c/ext",
                        "agent_trigger_run_id": "apirun_1",
                    },
                )
            return httpx.Response(
                200, json={"status": "completed", "conversation_url": "https://chatgpt.com/c/ext"}
            )
        return openai.handler(request)  # type: ignore[attr-defined]

    return httpx.MockTransport(handler)


async def test_workspace_agent_runs_natively_inside_origin(app, client, make_user) -> None:  # type: ignore[no-untyped-def]
    admin = await make_user("admin@example.com", role=Role.ADMIN)
    _provider, _ws, project = await setup_org(admin)
    seed = await admin.post(f"{ADMIN}/seed/agent-registry", json={"connection_type": "http"})
    assert seed.status_code == 200
    agents = {a["command"]: a for a in (await admin.get(f"{ADMIN}/agents")).json()}
    agent_id = agents["/resize"]["id"]

    # Phase 1 — the Workspace connection as it exists today
    res = await admin.put(
        f"{ADMIN}/agents/{agent_id}/connection",
        json={
            "connection_type": "chatgpt_workspace",
            "api_endpoint": TRIGGER,
            "api_key": "at-abcdefghijklmnop",
            "config": {},
        },
    )
    assert res.status_code == 200, res.text
    rt = res.json()["runtime"]
    assert rt["execution_mode"] == "workspace_trigger" and rt["workspace_agent_id"] == "agtch_abc123"
    assert rt["native_available"] is False

    # Phase 2 — origin_native cannot be switched on before the native runtime exists
    res = await admin.put(f"{ADMIN}/agents/{agent_id}/runtime", json={"execution_mode": "origin_native"})
    assert res.status_code == 422 and res.json()["error"]["code"] == "native_not_configured"
    res = await admin.put(
        f"{ADMIN}/agents/{agent_id}/runtime",
        json={
            "execution_mode": "workspace_trigger",
            "native_config": {"model": "gpt-5"},
            "native_api_key": "at-abcdefghijklmnop",
        },
    )
    assert res.status_code == 422 and res.json()["error"]["code"] == "invalid_api_key"
    res = await admin.put(
        f"{ADMIN}/agents/{agent_id}/runtime",
        json={
            "execution_mode": "workspace_trigger",
            "native_config": {
                "model": "gpt-5",
                "instructions": "You are Resize2. Adapt designs to the requested ratio.",
            },
            "native_api_key": "sk-platform-abcdefghijklmnop",
        },
    )
    assert res.status_code == 200, res.text
    rt = res.json()["runtime"]
    assert rt["native_available"] is True and rt["execution_mode"] == "workspace_trigger"
    assert rt["native_api_key_preview"].endswith("mnop") and "sk-platform" not in res.text

    openai_calls: list[dict[str, Any]] = []
    chatgpt_calls: list[str] = []
    app.state.adapters.http_transport = _mixed_transport(openai_calls, chatgpt_calls)
    try:
        # Phase 3 — Test Native Agent (brief §25): the image comes back inline, no chat is written
        res = await admin.client.post(
            f"{ADMIN}/agents/{agent_id}/test-native",
            headers=admin.headers,
            data={"prompt": "resize 16:9"},
            files={"file": ("original-design.png", png_bytes(), "image/png")},
        )
        assert res.status_code == 200, res.text
        out = res.json()
        assert out["ok"] and out["images"][0]["data_url"].startswith("data:image/png;base64,")
        assert out["text"] == "Here is your 4:5 poster." and out["response_id"] == "resp_img"
        assert openai_calls[-1]["instructions"].startswith("You are Resize2") and not chatgpt_calls
        assert openai_calls[-1]["input"][-1]["content"][1]["type"] == "input_image"

        conv = (
            await admin.post(f"/api/v1/projects/{project['id']}/conversations", json={"title": "MRFW"})
        ).json()
        up = await admin.client.post(
            f"/api/v1/projects/{project['id']}/assets",
            headers=admin.headers,
            files={"file": ("MRFW.png", png_bytes(), "image/png")},
            data={"kind": "image"},
        )

        # workspace_trigger: the run completes but the result is external (brief §4/§20)
        created = (
            await admin.post(
                f"/api/v1/conversations/{conv['id']}/runs",
                json={"content": "/resize resize 16:9", "selected_asset_ids": [up.json()["id"]]},
            )
        ).json()
        await drain(app)
        run = (await admin.get(f"/api/v1/runs/{created['run_id']}")).json()
        assert run["status"] == "SUCCEEDED" and run["result_json"]["result_type"] == "external_result"
        msg = (await admin.get(f"/api/v1/conversations/{conv['id']}/messages")).json()[-1]
        assert msg["metadata_json"]["result_type"] == "external_result"
        assert (
            msg["metadata_json"]["external_url"] == "https://chatgpt.com/c/ext" and msg["attachments"] == []
        )
        assert chatgpt_calls and not any(c.get("instructions") for c in openai_calls[1:])

        # Phase 4 — switch Resize to Origin Native
        res = await admin.put(
            f"{ADMIN}/agents/{agent_id}/runtime",
            json={
                "execution_mode": "origin_native",
                "native_config": {"model": "gpt-5", "instructions": "You are Resize2."},
            },
        )
        assert res.status_code == 200 and res.json()["runtime"]["execution_mode"] == "origin_native"
        chatgpt_calls.clear()
        openai_calls.clear()

        # acceptance (brief §28): /resize + image + "resize 16:9" → the actual image inside Origin
        created = (
            await admin.post(
                f"/api/v1/conversations/{conv['id']}/runs",
                json={"content": "/resize resize 16:9", "selected_asset_ids": [up.json()["id"]]},
            )
        ).json()
        await drain(app)
        run = (await admin.get(f"/api/v1/runs/{created['run_id']}")).json()
        assert run["status"] == "SUCCEEDED", run["error_json"]
        assert run["result_json"]["result_type"] == "native_result" and not chatgpt_calls
        assert [n["name"] for n in run["nodes"]] == [
            "Request received",
            "Resize Agent selected",
            "Conversation context loaded",
            "Source image loaded",
            "Resize Agent processing",
            "Output saved",
        ]
        history = (await admin.get(f"/api/v1/runs/{created['run_id']}/events/history")).json()
        types = [e["type"] for e in history]
        for t in (
            "agent.started",
            "tool.started",
            "artifact.preview",
            "tool.completed",
            "artifact.created",
            "run.completed",
        ):
            assert t in types, t
        msg = (await admin.get(f"/api/v1/conversations/{conv['id']}/messages")).json()[-1]
        assert msg["role"] == "assistant" and msg["metadata_json"]["result_type"] == "native_result"
        assert "ChatGPT" not in msg["content"] and "external_url" not in msg["metadata_json"]
        assert msg["attachments"][0]["mime_type"] == "image/png" and msg["attachments"][0]["artifact_id"]
        download = (
            await admin.get(f"/api/v1/artifacts/{msg['attachments'][0]['artifact_id']}/download")
        ).json()
        assert download["mime_type"] == "image/png"
        assert openai_calls[-1]["instructions"] == "You are Resize2."

        # second acceptance (brief §29): follow-up without re-uploading uses the current artifact
        created = (
            await admin.post(
                f"/api/v1/conversations/{conv['id']}/runs", json={"content": "Make the same design 4:5."}
            )
        ).json()
        await drain(app)
        run = (await admin.get(f"/api/v1/runs/{created['run_id']}")).json()
        assert (
            run["status"] == "SUCCEEDED" and [n["name"] for n in run["nodes"]][3] == "Current design loaded"
        )
        assert openai_calls[-1]["input"][-1]["content"][1]["type"] == "input_image"
        # refresh (brief §30): everything is persisted — messages, both results, the active agent
        messages = (await admin.get(f"/api/v1/conversations/{conv['id']}/messages")).json()
        assert [m["role"] for m in messages] == [
            "user",
            "assistant",
            "user",
            "assistant",
            "user",
            "assistant",
        ]
        assert sum(1 for m in messages if m["role"] == "assistant" and m["attachments"]) == 2
        conv_out = (await admin.get(f"/api/v1/conversations/{conv['id']}")).json()
        assert conv_out["active_agent"]["command"] == "/resize"
        assert conv_out["current_artifact_id"] == messages[-1]["attachments"][0]["artifact_id"]
    finally:
        app.state.adapters.http_transport = None
