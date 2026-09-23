"""`/agent` activates the agent for the conversation and its context window carries over."""

from __future__ import annotations

from app.domain.roles import Role
from app.models.chat import AgentSession
from sqlalchemy import select

from tests.api.test_runs import drain, make_agent, setup_org
from tests.conftest import requires_db

pytestmark = requires_db
ADMIN = "/api/v1/admin"


async def _run(admin, app, conv_id: str, content: str) -> dict:  # type: ignore[no-untyped-def]
    created = (await admin.post(f"/api/v1/conversations/{conv_id}/runs", json={"content": content})).json()
    await drain(app)
    return (await admin.get(f"/api/v1/runs/{created['run_id']}")).json()


async def test_slash_activates_agent_and_memory_carries_over(app, make_user) -> None:  # type: ignore[no-untyped-def]
    admin = await make_user("admin@example.com", role=Role.ADMIN)
    provider, ws, project = await setup_org(admin)
    copy = await make_agent(admin, provider, name="Copy Agent", command="/copy")
    qc = await make_agent(admin, provider, name="QC Agent", command="/qc")
    manager = await make_agent(
        admin, provider, name="Manager", command="/auto", is_manager=True, handoffs=[copy["id"], qc["id"]]
    )
    conv = (await admin.post(f"/api/v1/projects/{project['id']}/conversations", json={})).json()
    assert conv["active_agent"] is None and conv["memory"] == []

    # 1st turn: explicit /copy → agent runs and becomes the sticky agent
    run = await _run(admin, app, conv["id"], "/copy write a tagline for autumn")
    assert run["status"] == "SUCCEEDED" and run["entry_agent_id"] == copy["id"]
    conv = (await admin.get(f"/api/v1/conversations/{conv['id']}")).json()
    assert conv["active_agent"]["command"] == "/copy"
    assert conv["memory"][0]["agent_name"] == "Copy Agent" and conv["memory"][0]["turns"] == 1

    # 2nd turn: no command → still the Copy Agent, and it sees its previous turn (context window)
    run = await _run(admin, app, conv["id"], "make it shorter")
    assert run["entry_agent_id"] == copy["id"] and run["command"] == "/copy"
    msgs = (await admin.get(f"/api/v1/conversations/{conv['id']}/messages")).json()
    assert "memory: 1 earlier turn" in msgs[-1]["content"]
    history = (await admin.get(f"/api/v1/runs/{run['id']}/events/history")).json()
    assert any(
        e["type"] == "context.loaded"
        and "agent_memory:1_turns" in (e["payload"].get("context_sources") or [])
        for e in history
    )
    async with app.state.session_factory() as session:
        sess = (await session.scalars(select(AgentSession))).all()
        assert len(sess) == 1 and sess[0].turns == 2 and sess[0].chars > 0

    # switching to /qc: QC starts with its own empty memory; sticky agent changes
    run = await _run(admin, app, conv["id"], "/qc check the tagline")
    assert run["entry_agent_id"] == qc["id"]
    conv = (await admin.get(f"/api/v1/conversations/{conv['id']}")).json()
    assert conv["active_agent"]["command"] == "/qc" and {m["command"] for m in conv["memory"]} == {
        "/copy",
        "/qc",
    }
    msgs = (await admin.get(f"/api/v1/conversations/{conv['id']}/messages")).json()
    assert "memory:" not in msgs[-1]["content"]

    # /auto returns to the Manager and clears the sticky agent; plain messages go to the Manager again
    run = await _run(admin, app, conv["id"], "/auto plan everything")
    assert run["entry_agent_id"] == manager["id"]
    conv = (await admin.get(f"/api/v1/conversations/{conv['id']}")).json()
    assert conv["active_agent"] is None
    run = await _run(admin, app, conv["id"], "and now?")
    assert run["entry_agent_id"] == manager["id"]

    # bare /copy via the endpoint re-activates without running; memory can be cleared
    res = await admin.put(f"/api/v1/conversations/{conv['id']}/active-agent", json={"command": "/copy"})
    assert res.status_code == 200 and res.json()["active_agent"]["name"] == "Copy Agent"
    assert (
        await admin.put(f"/api/v1/conversations/{conv['id']}/active-agent", json={"command": "/nope"})
    ).status_code == 422
    res = await admin.delete(f"/api/v1/conversations/{conv['id']}/memory")
    assert res.status_code == 200 and res.json()["memory"] == []
    run = await _run(admin, app, conv["id"], "start fresh")
    assert run["entry_agent_id"] == copy["id"]
    msgs = (await admin.get(f"/api/v1/conversations/{conv['id']}/messages")).json()
    assert "memory:" not in msgs[-1]["content"]


async def test_default_provider_means_only_the_key_is_needed(app, make_user) -> None:  # type: ignore[no-untyped-def]
    admin = await make_user("admin@example.com", role=Role.ADMIN)
    provider, ws, project = await setup_org(admin)
    # an agent with NO provider/model publishes and runs on the organization default
    res = await admin.post(
        f"{ADMIN}/agents",
        json={
            "name": "Asset Agent",
            "command": "/asset",
            "version": {"instructions": "You organise assets."},
        },
    )
    agent = res.json()
    refused = await admin.post(f"{ADMIN}/agents/{agent['id']}/publish", json={})
    assert refused.status_code == 422 and any(
        "provider is required" in p for p in refused.json()["error"]["details"]
    )
    res = await admin.post(f"{ADMIN}/providers/{provider['id']}/set-default")
    assert res.status_code == 200 and res.json()["is_default"] is True
    assert (await admin.post(f"{ADMIN}/agents/{agent['id']}/publish", json={})).status_code == 200
    conv = (await admin.post(f"/api/v1/projects/{project['id']}/conversations", json={})).json()
    run = await _run(admin, app, conv["id"], "/asset list logos")
    assert run["status"] == "SUCCEEDED"
    msgs = (await admin.get(f"/api/v1/conversations/{conv['id']}/messages")).json()
    assert "echo-1" in msgs[-1]["content"]  # default model of the default provider

    # adopt: every agent switches to a newly connected provider in one call
    second = (await admin.post(f"{ADMIN}/providers", json={"name": "Echo Two", "type": "echo"})).json()
    await admin.put(
        f"{ADMIN}/providers/{second['id']}/models",
        json={"models": [{"model": "echo-1"}], "default_model": "echo-1"},
    )
    copy = await make_agent(admin, provider, name="Copy Agent", command="/copy")
    res = await admin.post(f"{ADMIN}/providers/{second['id']}/adopt")
    assert res.status_code == 200, res.text
    assert res.json()["switched"] >= 1 and res.json()["failed"] == 0
    detail = (await admin.get(f"{ADMIN}/agents/{copy['id']}")).json()
    assert (
        detail["active_version"]["provider_id"] == second["id"] and detail["active_version"]["version"] == 2
    )
    assert (await admin.get(f"{ADMIN}/providers")).json()[1]["is_default"] is True
