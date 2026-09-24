"""Admin console (docs/ADMIN_CONSOLE.md): overview, activity, test-message, delete."""

from __future__ import annotations

from typing import Any

from app.domain.roles import Role

from tests.api.test_runs import drain, setup_org
from tests.api.test_workspace_v0 import _agent_transport
from tests.conftest import requires_db

pytestmark = requires_db
ADMIN = "/api/v1/admin"


async def test_console_endpoints(app, client, make_user, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import app.core.ssrf as ssrf

    monkeypatch.setattr(ssrf, "resolve_host", lambda host: ["93.184.216.34"])
    admin = await make_user("console@example.com", role=Role.ADMIN)
    _provider, _ws, project = await setup_org(admin)
    calls: list[dict[str, Any]] = []
    app.state.adapters.http_transport = _agent_transport(calls)

    assert (
        await admin.post(f"{ADMIN}/seed/agent-registry", json={"connection_type": "http"})
    ).status_code == 200
    agents = {a["command"]: a for a in (await admin.get(f"{ADMIN}/agents")).json()}
    qc, agent8 = agents["/qc"], agents["/agent8"]
    res = await admin.put(
        f"{ADMIN}/agents/{qc['id']}/connection",
        json={
            "connection_type": "http",
            "api_endpoint": "https://agents.example.com/qc/run",
            "api_key": "qc-key-ABCDEF7890",
            "config": {"response_text_path": "reply"},
        },
    )
    assert res.status_code == 200, res.text

    # test-message goes through the gateway without creating a chat
    res = await admin.post(f"{ADMIN}/agents/{qc['id']}/test-message", json={"message": "ping from console"})
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["ok"] is True and "ping from console" in out["reply"] and out["session_native"] is True
    assert calls[-1]["path"] == "/qc/run" and calls[-1]["auth"] == "Bearer qc-key-ABCDEF7890"
    assert "qc-key" not in res.text
    # an unconfigured agent reports the failure as data, not as a 500
    res = await admin.post(f"{ADMIN}/agents/{agent8['id']}/test-message", json={"message": "hi"})
    assert res.status_code == 200 and res.json()["ok"] is False and res.json()["error_code"]

    # a real chat run, then the activity log and overview reflect it
    conv = (await admin.post(f"/api/v1/projects/{project['id']}/conversations", json={"title": "c"})).json()
    run = await admin.post(f"/api/v1/conversations/{conv['id']}/runs", json={"content": "/qc check this"})
    assert run.status_code == 202, run.text
    await drain(app)
    rows = (await admin.get(f"{ADMIN}/activity?agent_id={qc['id']}")).json()
    assert rows and rows[0]["status"] == "SUCCEEDED" and rows[0]["agent_command"] == "/qc"
    assert rows[0]["conversation_title"] and rows[0]["duration_ms"] is not None
    assert (await admin.get(f"{ADMIN}/activity?status=failed")).json() == []
    ov = (await admin.get(f"{ADMIN}/overview")).json()
    assert ov["agents_total"] >= 8 and ov["agents_connected"] >= 1 and ov["runs_24h"] >= 1
    assert ov["runs_24h_succeeded"] >= 1 and ov["recent_failures"] == []

    # delete: unused agent goes away, used agent is refused
    assert (await admin.delete(f"{ADMIN}/agents/{agent8['id']}")).status_code == 204
    assert (await admin.get(f"{ADMIN}/agents/{agent8['id']}")).status_code == 404
    res = await admin.delete(f"{ADMIN}/agents/{qc['id']}")
    assert res.status_code == 409 and res.json()["error"]["code"] == "agent_in_use"
    # a member cannot reach the console
    member = await make_user("member@example.com", role=Role.MEMBER)
    assert (await member.get(f"{ADMIN}/overview")).status_code in (401, 403)
