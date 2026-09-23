"""Origin Agent Workspace V0 (§41 definition of done) against a mocked existing agent."""

from __future__ import annotations

import json
from typing import Any

import httpx
from app.domain.roles import Role
from app.models.chat import AgentSession
from sqlalchemy import select

from tests.api.test_runs import drain, png_bytes, setup_org
from tests.conftest import requires_db

pytestmark = requires_db
ADMIN = "/api/v1/admin"


def _agent_transport(calls: list[dict[str, Any]]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        calls.append({"path": request.url.path, "auth": request.headers.get("authorization"), "body": body})
        turn = len([c for c in calls if c["path"].endswith("/run")])
        if request.url.path.endswith("/fail"):
            return httpx.Response(503, json={"error": "down"})
        return httpx.Response(
            200,
            json={
                "reply": f"[{request.url.path.split('/')[-2]}] turn {turn}: {body.get('message')}",
                "session_id": f"sess-{turn}",
                "files": [{"name": "out.png", "mime_type": "image/png", "data": "aGVsbG8="}]
                if turn == 1
                else [],
            },
        )

    return httpx.MockTransport(handler)


async def test_v0_definition_of_done(app, client, make_user, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import app.core.ssrf as ssrf

    monkeypatch.setattr(ssrf, "resolve_host", lambda host: ["93.184.216.34"])
    admin = await make_user("admin@example.com", role=Role.ADMIN)
    provider, ws, project = await setup_org(admin)

    # Phase 2 — registry + one real (mocked) agent connection, key encrypted and masked
    seed = await admin.post(f"{ADMIN}/seed/agent-registry", json={"connection_type": "http"})
    assert seed.status_code == 200 and seed.json()["created"] == 8
    agents = {a["command"]: a for a in (await admin.get(f"{ADMIN}/agents")).json()}
    assert (
        agents["/resize"]["connection"]["connection_type"] == "http"
        and agents["/resize"]["status"] == "draft"
    )
    res = await admin.put(
        f"{ADMIN}/agents/{agents['/resize']['id']}/connection",
        json={
            "connection_type": "http",
            "api_endpoint": "https://agents.example.com/resize/run",
            "api_key": "resize-key-ABCDEF7890",
            "config": {"response_text_path": "reply"},
        },
    )
    assert res.status_code == 200, res.text
    resize = res.json()
    assert (
        resize["status"] == "active"
        and resize["connection"]["api_key_preview"].endswith("7890")
        and "resize-key" not in res.text
    )
    res = await admin.put(
        f"{ADMIN}/agents/{agents['/qc']['id']}/connection",
        json={
            "connection_type": "http",
            "api_endpoint": "https://agents.example.com/qc/run",
            "api_key": "qc-key-ABCDEF7890",
        },
    )
    assert res.status_code == 200
    calls: list[dict[str, Any]] = []
    app.state.adapters.http_transport = _agent_transport(calls)
    try:
        # connection test uses the real endpoint contract (mocked here)
        t = await admin.post(f"{ADMIN}/agents/{resize['id']}/test-connection")
        assert t.status_code == 200 and t.json()["success"] is True and t.json()["status"] == "connected"
        assert (await admin.get(f"{ADMIN}/agents/{resize['id']}")).json()["connection"][
            "connection_status"
        ] == "ok"
        calls.clear()

        # Phase 3/5 — chat: /resize with a file → real agent called, response streamed, artifact saved
        member = await make_user("designer@example.com", role=Role.MEMBER)
        await admin.post(
            f"/api/v1/workspaces/{ws['id']}/members", json={"email": "designer@example.com", "role": "member"}
        )
        conv = (
            await member.post(
                f"/api/v1/projects/{project['id']}/conversations", json={"title": "Instagram Resize"}
            )
        ).json()
        up = await member.client.post(
            f"/api/v1/projects/{project['id']}/assets",
            headers=member.headers,
            files={"file": ("master.png", png_bytes(), "image/png")},
            data={"kind": "image"},
        )
        asset = up.json()
        created = (
            await member.post(
                f"/api/v1/conversations/{conv['id']}/runs",
                json={
                    "content": "/resize Convert the approved master design into 4:5 and 9:16.",
                    "selected_asset_ids": [asset["id"]],
                },
            )
        ).json()
        await drain(app)
        run = (await member.get(f"/api/v1/runs/{created['run_id']}")).json()
        assert run["status"] == "SUCCEEDED", run["error_json"]
        assert [n["name"] for n in run["nodes"]] == [
            "Request received",
            "Resize Agent selected",
            "Conversation context loaded",
            "Files prepared",
            "Resize Agent processing",
            "Output saved",
        ]
        assert all(n["status"] == "SUCCEEDED" for n in run["nodes"])
        call = calls[-1]
        assert call["path"] == "/resize/run" and call["auth"] == "Bearer resize-key-ABCDEF7890"
        assert call["body"]["message"].startswith("Convert the approved") and call["body"]["session_id"] == ""
        assert (
            call["body"]["files"][0]["name"] == "master.png"
            and call["body"]["files"][0]["mime_type"] == "image/png"
        )
        history = (await member.get(f"/api/v1/runs/{created['run_id']}/events/history")).json()
        types = [e["type"] for e in history]
        for t in (
            "run.started",
            "agent.selected",
            "context.loaded",
            "files.prepared",
            "agent.started",
            "response.streaming",
            "artifact.created",
            "run.completed",
        ):
            assert t in types, t
        assert "resize-key" not in json.dumps(history)
        msgs = (await member.get(f"/api/v1/conversations/{conv['id']}/messages")).json()
        assert (
            msgs[-1]["role"] == "assistant"
            and msgs[-1]["agent_name"] == "Resize Agent"
            and "turn 1" in msgs[-1]["content"]
        )
        assert msgs[-1]["attachments"] and msgs[-1]["attachments"][0]["artifact_id"]

        # Phase 4 — follow-up without a command continues the same agent with its native session id
        created = (
            await member.post(
                f"/api/v1/conversations/{conv['id']}/runs", json={"content": "Make the heading smaller."}
            )
        ).json()
        await drain(app)
        assert (await member.get(f"/api/v1/runs/{created['run_id']}")).json()["status"] == "SUCCEEDED"
        assert calls[-1]["path"] == "/resize/run" and calls[-1]["body"]["session_id"] == "sess-1"
        async with app.state.session_factory() as session:
            sess = (await session.scalars(select(AgentSession))).all()
            assert len(sess) == 1 and sess[0].provider_session_id == "sess-2"
        conversation = (await member.get(f"/api/v1/conversations/{conv['id']}")).json()
        assert conversation["active_agent"]["command"] == "/resize"

        # switching agents: /qc gets the current request + bounded context, its own (empty) session
        created = (
            await member.post(
                f"/api/v1/conversations/{conv['id']}/runs", json={"content": "/qc Check this design."}
            )
        ).json()
        await drain(app)
        assert (await member.get(f"/api/v1/runs/{created['run_id']}")).json()["status"] == "SUCCEEDED"
        qc_call = calls[-1]
        assert (
            qc_call["path"] == "/qc/run"
            and qc_call["body"]["session_id"] == ""
            and 1 <= len(qc_call["body"]["history"]) <= 12
        )
        assert any(h["content"].startswith("[Resize Agent]") for h in qc_call["body"]["history"])
        conversation = (await member.get(f"/api/v1/conversations/{conv['id']}")).json()
        assert conversation["active_agent"]["command"] == "/qc"

        # unknown command → recoverable error listing available agents; nothing lost
        bad = await member.post(f"/api/v1/conversations/{conv['id']}/runs", json={"content": "/nope hello"})
        assert bad.status_code == 422 and bad.json()["error"]["code"] == "agent_unavailable"

        # agent failure → run failed with a safe message, retry works
        await admin.put(
            f"{ADMIN}/agents/{agents['/qc']['id']}/connection",
            json={"connection_type": "http", "api_endpoint": "https://agents.example.com/qc/fail"},
        )
        created = (
            await member.post(f"/api/v1/conversations/{conv['id']}/runs", json={"content": "/qc again"})
        ).json()
        await drain(app)
        failed = (await member.get(f"/api/v1/runs/{created['run_id']}")).json()
        assert (
            failed["status"] == "FAILED"
            and failed["error_json"]["code"] == "agent_unavailable"
            and "Retry" in failed["error_json"]["message"]
        )
        await admin.put(
            f"{ADMIN}/agents/{agents['/qc']['id']}/connection",
            json={"connection_type": "http", "api_endpoint": "https://agents.example.com/qc/run"},
        )
        retried = await member.post(f"/api/v1/runs/{created['run_id']}/retry")
        assert retried.status_code == 200
        await drain(app)
        assert (await member.get(f"/api/v1/runs/{created['run_id']}")).json()["status"] == "SUCCEEDED"
        msgs = (await member.get(f"/api/v1/conversations/{conv['id']}/messages")).json()
        assert (
            sum(1 for m in msgs if m["role"] == "user" and m["content"] == "/qc again") == 1
        )  # not duplicated
    finally:
        app.state.adapters.http_transport = None

    # Phase 7 — My Work after "logging in again"
    login = await client.post(
        "/api/v1/auth/login", json={"email": "designer@example.com", "password": "Password123!"}
    )
    fresh = member.__class__(
        client,
        member.email,
        login.json()["access_token"],
        login.json()["refresh_token"],
        member.organization_id,
    )
    work = (await fresh.get("/api/v1/work")).json()
    item = next(w for w in work if w["conversation_id"] == conv["id"])
    assert item["title"] == "Instagram Resize" and item["files"] == 1 and item["outputs"] == 1
    assert {a["command"] for a in item["agents_used"]} == {"/resize", "/qc"} and item["messages"] >= 8
    assert (await fresh.get("/api/v1/work?search=heading")).json()[0]["conversation_id"] == conv["id"]
    assert (await fresh.get("/api/v1/work?search=master.png")).json()[0]["conversation_id"] == conv["id"]
    assert (await fresh.get(f"/api/v1/work?agent_id={agents['/qc']['id']}")).json()[0][
        "conversation_id"
    ] == conv["id"]
    assert (await fresh.get("/api/v1/work?search=nothing-here")).json() == []
    detail = (await fresh.get(f"/api/v1/work/{conv['id']}")).json()
    assert detail["primary_agent"] in ("Resize Agent", "Design QC Agent")
