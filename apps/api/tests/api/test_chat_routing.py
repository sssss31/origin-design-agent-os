"""Slash-command routing rules (brief §2, §4, §13): bare commands select, prompts never carry the
command, agent switches are persistent system events, stale runs surface Retry."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.domain.roles import Role
from sqlalchemy import select

from tests.api.test_runs import drain, setup_org
from tests.api.test_workspace_v0 import _agent_transport
from tests.conftest import requires_db

pytestmark = requires_db
ADMIN = "/api/v1/admin"


async def _connected_registry(app, admin, calls):  # type: ignore[no-untyped-def]
    app.state.adapters.http_transport = _agent_transport(calls)
    assert (
        await admin.post(f"{ADMIN}/seed/agent-registry", json={"connection_type": "http"})
    ).status_code == 200
    agents = {a["command"]: a for a in (await admin.get(f"{ADMIN}/agents")).json()}
    for cmd in ("/resize", "/qc"):
        res = await admin.put(
            f"{ADMIN}/agents/{agents[cmd]['id']}/connection",
            json={
                "connection_type": "http",
                "api_endpoint": f"https://agents.example.com/{cmd.strip('/')}/run",
                "api_key": f"{cmd.strip('/')}-key-ABCDEF7890",
                "config": {"response_text_path": "reply"},
            },
        )
        assert res.status_code == 200, res.text
    return agents


async def test_bare_command_selects_without_a_run_and_prompts_are_clean(
    app, client, make_user, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    import app.core.ssrf as ssrf

    monkeypatch.setattr(ssrf, "resolve_host", lambda host: ["93.184.216.34"])
    admin = await make_user("routing@example.com", role=Role.ADMIN)
    _p, _w, project = await setup_org(admin)
    calls: list[dict[str, Any]] = []
    await _connected_registry(app, admin, calls)
    conv = (await admin.post(f"/api/v1/projects/{project['id']}/conversations", json={})).json()

    # CASE A: "/resize" alone must not become a run or a prompt
    res = await admin.post(f"/api/v1/conversations/{conv['id']}/runs", json={"content": "/resize"})
    assert res.status_code == 422 and res.json()["error"]["code"] == "empty_prompt", res.text
    assert (await admin.get(f"/api/v1/conversations/{conv['id']}/messages")).json() == []
    res = await admin.put(f"/api/v1/conversations/{conv['id']}/active-agent", json={"command": "/resize"})
    assert res.status_code == 200 and res.json()["active_agent"]["command"] == "/resize"
    messages = (await admin.get(f"/api/v1/conversations/{conv['id']}/messages")).json()
    assert [m["role"] for m in messages] == ["system"] and messages[0]["content"] == "Resize Agent selected"
    assert messages[0]["metadata_json"]["event"] == "agent.selected"

    # CASE B: "/resize text" → the agent receives only the text
    res = await admin.post(
        f"/api/v1/conversations/{conv['id']}/runs", json={"content": "/resize make it 4:5"}
    )
    assert res.status_code == 202, res.text
    await drain(app)
    assert calls[-1]["path"] == "/resize/run" and calls[-1]["body"]["message"] == "make it 4:5"
    run = (await admin.get(f"/api/v1/runs/{res.json()['run_id']}")).json()
    assert run["status"] == "SUCCEEDED" and run["user_input"] == "make it 4:5"
    conv_now = (await admin.get(f"/api/v1/conversations/{conv['id']}")).json()
    assert conv_now["title"] == "Resize: make it 4:5"

    # CASE C: follow-up without a command stays with the agent, history carries no slash commands
    res = await admin.post(f"/api/v1/conversations/{conv['id']}/runs", json={"content": "and 9:16 too"})
    assert res.status_code == 202
    await drain(app)
    assert calls[-1]["path"] == "/resize/run" and calls[-1]["body"]["message"] == "and 9:16 too"
    # the agent keeps its own session: the stored session id continues the same thread
    assert calls[-1]["body"]["session_id"] == "sess-1"
    assert "/resize" not in " ".join(h["content"] for h in calls[-1]["body"].get("history", []))

    # CASE D: "/qc text" switches agent; both agents' turns stay in one conversation
    res = await admin.post(f"/api/v1/conversations/{conv['id']}/runs", json={"content": "/qc check both"})
    assert res.status_code == 202
    await drain(app)
    assert calls[-1]["path"] == "/qc/run" and calls[-1]["body"]["message"] == "check both"
    messages = (await admin.get(f"/api/v1/conversations/{conv['id']}/messages")).json()
    roles = [m["role"] for m in messages]
    assert roles.count("user") == 3 and roles.count("assistant") == 3
    agents_in_thread = {m["agent_command"] for m in messages if m["role"] == "assistant"}
    assert agents_in_thread == {"/resize", "/qc"}
    # the message that failed never disappears: an unknown command is rejected before anything is stored
    res = await admin.post(f"/api/v1/conversations/{conv['id']}/runs", json={"content": "/nope do it"})
    assert res.status_code == 422 and res.json()["error"]["code"] == "agent_unavailable"
    assert len((await admin.get(f"/api/v1/conversations/{conv['id']}/messages")).json()) == len(messages)


async def test_stale_running_run_is_reaped_so_retry_appears(app, client, make_user, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import app.core.ssrf as ssrf
    from app.models.workflows import WorkflowRun

    monkeypatch.setattr(ssrf, "resolve_host", lambda host: ["93.184.216.34"])
    admin = await make_user("stale@example.com", role=Role.ADMIN)
    _p, _w, project = await setup_org(admin)
    calls: list[dict[str, Any]] = []
    await _connected_registry(app, admin, calls)
    conv = (await admin.post(f"/api/v1/projects/{project['id']}/conversations", json={})).json()
    res = await admin.post(f"/api/v1/conversations/{conv['id']}/runs", json={"content": "/qc hi"})
    run_id = res.json()["run_id"]
    await drain(app)
    # simulate an executor that died mid-run: RUNNING with an old heartbeat and no new events
    async with app.state.session_factory() as session:
        run = await session.scalar(select(WorkflowRun).where(WorkflowRun.id == run_id))
        run.status = "RUNNING"
        run.heartbeat_at = datetime.now(UTC) - timedelta(hours=1)
        await session.execute(
            __import__("sqlalchemy").text(
                "UPDATE execution_events SET occurred_at = now() - interval '1 hour' WHERE run_id = :r"
            ),
            {"r": str(run_id)},
        )
        await session.commit()
    run_out = (await admin.get(f"/api/v1/runs/{run_id}")).json()
    assert run_out["status"] == "FAILED" and run_out["error_json"]["code"] == "interrupted"
    assert run_out["error_json"]["retryable"] is True
    # and Retry re-runs the same stored message
    res = await admin.post(f"/api/v1/runs/{run_id}/retry")
    assert res.status_code == 200, res.text
