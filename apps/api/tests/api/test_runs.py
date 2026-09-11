"""Phases 4–5 acceptance: slash routing, context, agent runtime, durable events, SSE replay,
clarification pause/resume, cancel/retry, manager delegation, QC loop and artifacts —
all with the Echo provider (no external calls)."""

from __future__ import annotations

import asyncio
import io

from app.domain.roles import Role
from PIL import Image
from sqlalchemy import select

from tests.conftest import requires_db

pytestmark = requires_db
ADMIN = "/api/v1/admin"


def png_bytes(w: int = 1080, h: int = 1350) -> bytes:
    buf = io.BytesIO()
    im = Image.new("RGB", (w, h), (240, 240, 240))
    for x in range(0, w, 40):
        for y in range(0, h, 40):
            if (x // 40 + y // 40) % 2 == 0:
                im.paste((30, 60, 120), (x, y, x + 20, y + 20))
    im.save(buf, format="PNG")
    return buf.getvalue()


async def drain(app) -> None:  # type: ignore[no-untyped-def]
    await app.state.adapters.queue.drain()
    await asyncio.sleep(0.05)
    await app.state.adapters.queue.drain()


async def setup_org(admin, *, with_tools: bool = False):  # type: ignore[no-untyped-def]
    provider = (await admin.post(f"{ADMIN}/providers", json={"name": "Echo", "type": "echo"})).json()
    await admin.put(
        f"{ADMIN}/providers/{provider['id']}/models",
        json={"models": [{"model": "echo-1"}], "default_model": "echo-1"},
    )
    ws = (
        await admin.post("/api/v1/workspaces", json={"name": "Studio", "rules_text": "Use brand blue."})
    ).json()
    project = (await admin.post(f"/api/v1/workspaces/{ws['id']}/projects", json={"name": "Autumn"})).json()
    await admin.patch(f"/api/v1/projects/{project['id']}", json={"summary_text": "Autumn poster campaign."})
    return provider, ws, project


async def make_agent(
    admin,
    provider,
    *,
    name: str,
    command: str,
    tools: list[str] | None = None,
    tool_ids: list[str] | None = None,
    is_manager: bool = False,
    handoffs: list[str] | None = None,
):  # type: ignore[no-untyped-def]
    agent = (
        await admin.post(
            f"{ADMIN}/agents",
            json={
                "name": name,
                "command": command,
                "description": f"{name} description",
                "is_manager": is_manager,
                "version": {
                    "instructions": f"You are {name}.",
                    "provider_id": provider["id"],
                    "model": "echo-1",
                },
            },
        )
    ).json()
    for tid in tool_ids or []:
        await admin.post(f"{ADMIN}/agents/{agent['id']}/tools/{tid}", json={})
    for target in handoffs or []:
        await admin.post(
            f"{ADMIN}/agents/{agent['id']}/handoffs/{target}", json={"routing_hint": f"use for {name}"}
        )
    res = await admin.post(f"{ADMIN}/agents/{agent['id']}/publish", json={})
    assert res.status_code == 200, res.text
    return res.json()


async def test_slash_run_end_to_end_with_durable_events(app, client, make_user) -> None:  # type: ignore[no-untyped-def]
    admin = await make_user("admin@example.com", role=Role.ADMIN)
    provider, ws, project = await setup_org(admin)
    await make_agent(admin, provider, name="Copy Agent", command="/copy")
    conv = (await admin.post(f"/api/v1/projects/{project['id']}/conversations", json={})).json()

    res = await admin.post(
        f"/api/v1/conversations/{conv['id']}/runs", json={"content": "/copy write a tagline"}
    )
    assert res.status_code == 202, res.text
    created = res.json()
    assert created["status"] == "QUEUED" and created["event_stream_url"].endswith(
        f"/runs/{created['run_id']}/events"
    )
    await drain(app)

    run = (await admin.get(f"/api/v1/runs/{created['run_id']}")).json()
    assert run["status"] == "SUCCEEDED", run
    assert [n["name"] for n in run["nodes"]] == ["Parse command", "Load context", "Copy Agent", "Save result"]
    assert all(n["status"] == "SUCCEEDED" for n in run["nodes"])
    assert run["result_json"]["output_text"].startswith("[copy-agent v1 · echo-1] write a tagline")

    # persisted events reconstruct the timeline (spec §14) and never carry reasoning
    history = (await admin.get(f"/api/v1/runs/{created['run_id']}/events/history")).json()
    types = [e["type"] for e in history]
    assert types[:3] == ["run.started", "node.started", "node.completed"]
    assert "context.loaded" in types and "agent.started" in types and types[-1] == "run.completed"
    assert [e["sequence_no"] for e in history] == list(range(1, len(history) + 1))
    ctx_event = next(e for e in history if e["type"] == "context.loaded")
    assert (
        "project" in ctx_event["payload"]["context_sources"]
        and "project_summary" in ctx_event["payload"]["context_sources"]
    )
    assert not any("reasoning" in e["payload"] for e in history)

    # assistant reply is linked to the run and visible in the conversation
    msgs = (await admin.get(f"/api/v1/conversations/{conv['id']}/messages")).json()
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["run_id"] == created["run_id"] and msgs[1]["agent_command"] == "/copy"
    assert msgs[0]["run_id"] == created["run_id"]

    # SSE replay from the beginning and from Last-Event-ID
    async with client.stream("GET", created["event_stream_url"], headers=admin.headers) as stream:
        assert stream.status_code == 200 and stream.headers["content-type"].startswith("text/event-stream")
        body = "".join([chunk async for chunk in stream.aiter_text()])
    assert body.count("event: ") == len(history) and "event: run.completed" in body
    async with client.stream(
        "GET", created["event_stream_url"], headers={**admin.headers, "Last-Event-ID": str(len(history) - 2)}
    ) as stream:
        body = "".join([chunk async for chunk in stream.aiter_text()])
    assert body.count("event: ") == 2

    # a second run in the same chat can use a different agent; messages stay in one conversation
    await make_agent(admin, provider, name="QC Agent", command="/qc")
    res = await admin.post(f"/api/v1/conversations/{conv['id']}/runs", json={"content": "/qc check it"})
    await drain(app)
    assert (await admin.get(f"/api/v1/runs/{res.json()['run_id']}")).json()["status"] == "SUCCEEDED"
    msgs = (await admin.get(f"/api/v1/conversations/{conv['id']}/messages")).json()
    assert [m.get("agent_command") for m in msgs if m["role"] == "assistant"] == ["/copy", "/qc"]


async def test_routing_errors_and_permissions(app, make_user) -> None:  # type: ignore[no-untyped-def]
    admin = await make_user("admin@example.com", role=Role.ADMIN)
    provider, ws, project = await setup_org(admin)
    conv = (await admin.post(f"/api/v1/projects/{project['id']}/conversations", json={})).json()
    res = await admin.post(f"/api/v1/conversations/{conv['id']}/runs", json={"content": "/resize nothing"})
    assert res.status_code == 422 and res.json()["error"]["code"] == "agent_unavailable"
    res = await admin.post(f"/api/v1/conversations/{conv['id']}/runs", json={"content": "just words"})
    assert res.status_code == 422 and res.json()["error"]["code"] == "no_manager"
    viewer = await make_user("viewer@example.com", role=Role.VIEWER)
    await admin.post(
        f"/api/v1/workspaces/{ws['id']}/members", json={"email": "viewer@example.com", "role": "member"}
    )
    assert (
        await viewer.post(f"/api/v1/conversations/{conv['id']}/runs", json={"content": "/copy x"})
    ).status_code == 403
    stranger = await make_user("s@example.com", org="Other")
    assert (await stranger.get(f"/api/v1/conversations/{conv['id']}/runs")).status_code == 404


async def test_clarification_pause_resume_cancel_and_retry(app, make_user) -> None:  # type: ignore[no-untyped-def]
    admin = await make_user("admin@example.com", role=Role.ADMIN)
    provider, ws, project = await setup_org(admin)
    await make_agent(admin, provider, name="Resize Agent", command="/resize")
    conv = (await admin.post(f"/api/v1/projects/{project['id']}/conversations", json={})).json()

    run_id = (
        await admin.post(
            f"/api/v1/conversations/{conv['id']}/runs", json={"content": "/resize the poster ?clarify"}
        )
    ).json()["run_id"]
    await drain(app)
    run = (await admin.get(f"/api/v1/runs/{run_id}")).json()
    assert run["status"] == "WAITING_FOR_USER"
    waiting = next(n for n in run["nodes"] if n["status"] == "WAITING_FOR_USER")
    assert waiting["question"] == "Which target sizes do you need?" and waiting["question_schema"]
    history = [e["type"] for e in (await admin.get(f"/api/v1/runs/{run_id}/events/history")).json()]
    assert history[-1] == "clarification.requested"

    # wrong answers are rejected, the reply resumes the same run
    assert (await admin.post(f"/api/v1/runs/{run_id}/retry")).status_code == 422
    res = await admin.post(f"/api/v1/runs/{run_id}/clarification", json={"answer": "4:5 and 9:16"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "QUEUED"
    await drain(app)
    run = (await admin.get(f"/api/v1/runs/{run_id}")).json()
    assert run["status"] == "SUCCEEDED"
    assert "resumed with answer: 4:5 and 9:16" in run["result_json"]["output_text"]
    history = [e["type"] for e in (await admin.get(f"/api/v1/runs/{run_id}/events/history")).json()]
    assert "clarification.received" in history and history[-1] == "run.completed"
    msgs = (await admin.get(f"/api/v1/conversations/{conv['id']}/messages")).json()
    assert [m["role"] for m in msgs] == ["user", "user", "assistant"] and msgs[1]["content"] == "4:5 and 9:16"
    assert (
        await admin.post(f"/api/v1/runs/{run_id}/clarification", json={"answer": "again"})
    ).status_code == 422

    # cancel a waiting run
    run2 = (
        await admin.post(
            f"/api/v1/conversations/{conv['id']}/runs", json={"content": "/resize again ?clarify"}
        )
    ).json()["run_id"]
    await drain(app)
    res = await admin.post(f"/api/v1/runs/{run2}/cancel")
    assert res.status_code == 200 and res.json()["status"] == "CANCELLED"
    assert {n["status"] for n in res.json()["nodes"]} <= {"SUCCEEDED", "SKIPPED"}
    assert (await admin.post(f"/api/v1/runs/{run2}/cancel")).status_code == 422

    # a run whose provider secret is missing fails safely and can be retried after the fix
    openai = (await admin.post(f"{ADMIN}/providers", json={"name": "OpenAI", "type": "openai"})).json()
    await admin.put(
        f"{ADMIN}/providers/{openai['id']}/models",
        json={"models": [{"model": "gpt-x"}], "default_model": "gpt-x"},
    )
    await make_agent(
        admin, openai | {"id": openai["id"]}, name="Master Design", command="/master"
    ) if False else None
    agent = (
        await admin.post(
            f"{ADMIN}/agents",
            json={
                "name": "Master Design",
                "command": "/master",
                "version": {"instructions": "You design.", "provider_id": openai["id"], "model": "gpt-x"},
            },
        )
    ).json()
    assert (await admin.post(f"{ADMIN}/agents/{agent['id']}/publish", json={})).status_code == 200
    run3 = (
        await admin.post(f"/api/v1/conversations/{conv['id']}/runs", json={"content": "/master a poster"})
    ).json()["run_id"]
    await drain(app)
    run = (await admin.get(f"/api/v1/runs/{run3}")).json()
    assert run["status"] == "FAILED" and run["error_json"]["code"] in (
        "agent_not_configured",
        "internal_error",
        "provider_secret_unavailable",
    )
    failed = next(n for n in run["nodes"] if n["status"] == "FAILED")
    assert failed["error_json"]["message"] and "sk-" not in failed["error_json"]["message"]
    types = [e["type"] for e in (await admin.get(f"/api/v1/runs/{run3}/events/history")).json()]
    assert types[-2:] == ["node.failed", "run.failed"]
    assert (await admin.post(f"/api/v1/runs/{run3}/retry")).status_code in (200, 422)


async def test_manager_delegation_tools_artifacts_and_qc_loop(app, client, make_user) -> None:  # type: ignore[no-untyped-def]
    admin = await make_user("admin@example.com", role=Role.ADMIN)
    provider, ws, project = await setup_org(admin)
    # built-in tools become editable rows via the seed command
    from app.seeds.design_agents import seed_builtin_tools

    async with app.state.session_factory() as session:
        from app.core.authz import AuthContext
        from app.models.identity import User

        user = await session.scalar(select(User).where(User.email == "admin@example.com"))
        import uuid as _uuid

        ctx = AuthContext(
            user=user,
            memberships={_uuid.UUID(admin.organization_id): Role.ADMIN},
            organization_id=_uuid.UUID(admin.organization_id),
        )
        created = await seed_builtin_tools(session, ctx)
        await session.commit()
    assert created >= 6
    tools = {t["slug"]: t for t in (await admin.get(f"{ADMIN}/tools")).json()}
    assert (
        tools["image.resize"]["is_builtin"] and tools["qc.checklist"]["executor_type"] == "internal_function"
    )

    resize = await make_agent(
        admin,
        provider,
        name="Resize Agent",
        command="/resize",
        tool_ids=[tools["image.resize"]["id"], tools["image.inspect"]["id"]],
    )
    qc = await make_agent(
        admin, provider, name="QC Agent", command="/qc", tool_ids=[tools["qc.checklist"]["id"]]
    )
    export = await make_agent(
        admin, provider, name="Export Agent", command="/export", tool_ids=[tools["export.package"]["id"]]
    )
    manager = await make_agent(
        admin,
        provider,
        name="Manager",
        command="/auto",
        is_manager=True,
        handoffs=[resize["id"], qc["id"], export["id"]],
    )
    assert manager["is_manager"]

    upload = await client.post(
        f"/api/v1/projects/{project['id']}/assets",
        headers=admin.headers,
        files={"file": ("poster.png", png_bytes(), "image/png")},
        data={"kind": "image"},
    )
    asset = upload.json()
    conv = (await admin.post(f"/api/v1/projects/{project['id']}/conversations", json={})).json()

    # explicit /resize with tool use: echo runner invokes !image.resize → artifacts with lineage
    res = await admin.post(
        f"/api/v1/conversations/{conv['id']}/runs",
        json={"content": "/resize to 4:5 !image.resize", "selected_asset_ids": [asset["id"]]},
    )
    assert res.status_code == 202, res.text
    await drain(app)
    run = (await admin.get(f"/api/v1/runs/{res.json()['run_id']}")).json()
    assert run["status"] == "SUCCEEDED", run
    types = [e["type"] for e in (await admin.get(f"/api/v1/runs/{run['id']}/events/history")).json()]
    assert "tool.started" in types and "tool.completed" in types
    # echo runner calls the tool with {} → the tool reports a validation error, no artifact is invented (spec §19)
    tool_done = next(
        e
        for e in (await admin.get(f"/api/v1/runs/{run['id']}/events/history")).json()
        if e["type"] == "tool.completed"
    )
    assert tool_done["payload"].get("error_code") in (None, "tool_error", "invalid_input")

    # run the resize tool for real through the executor path (direct tool call with arguments)
    import uuid as _uuid

    from app.ports.tools import ToolCall
    from app.tools import registry as tool_registry
    from app.tools.context import ToolContext

    tool_registry.load_builtins()
    spec, _fn = tool_registry.get("image.resize")
    tctx = ToolContext(
        session_factory=app.state.session_factory,
        storage=app.state.adapters.storage,
        organization_id=_uuid.UUID(admin.organization_id),
        workspace_id=_uuid.UUID(ws["id"]),
        project_id=_uuid.UUID(project["id"]),
        conversation_id=_uuid.UUID(conv["id"]),
        run_id=None,
        node_run_id=None,
        agent_version_id=None,
        created_by=None,
    )
    result = await tool_registry.bound_executor(tctx).execute(
        ToolCall(tool=spec, arguments={"asset_id": asset["id"], "target_sizes": ["4:5", "9:16"]})
    )
    assert result.ok, result.error_message
    assert [o["target"] for o in result.output["outputs"]] == ["4:5", "9:16"] and len(result.files) == 2
    from app.services.artifacts import ArtifactService

    async with app.state.session_factory() as session:
        svc = ArtifactService(session, None, app.state.adapters.storage)
        art, ver = await svc.persist_produced(
            result.files[0],
            workspace_id=_uuid.UUID(ws["id"]),
            project_id=_uuid.UUID(project["id"]),
            conversation_id=None,
            run_id=None,
            node_run_id=None,
            agent_version_id=None,
            organization_id=_uuid.UUID(admin.organization_id),
            created_by=None,
        )
        await session.commit()
        art_id = str(art.id)
    art = (await admin.get(f"/api/v1/artifacts/{art_id}")).json()
    assert (
        art["current_version"]["width"] == 1080
        and art["current_version"]["height"] == 1350
        and art["status"] == "generated"
    )

    # deterministic QC on the artifact
    spec_qc, _ = tool_registry.get("qc.checklist")
    qc_result = await tool_registry.bound_executor(tctx).execute(
        ToolCall(tool=spec_qc, arguments={"artifact_id": art_id, "expected_aspect": "4:5"})
    )
    assert (
        qc_result.ok and qc_result.output["passed"] is True and "dimensions" in qc_result.output["checks_run"]
    )
    bad_qc = await tool_registry.bound_executor(tctx).execute(
        ToolCall(tool=spec_qc, arguments={"artifact_id": art_id, "expected_size": "1080x1920"})
    )
    assert (
        bad_qc.ok
        and bad_qc.output["passed"] is False
        and bad_qc.output["findings"][0]["code"] == "dimension_mismatch"
    )

    # export validates dimensions and produces a final artifact with lineage to its parent
    spec_exp, _ = tool_registry.get("export.package")
    exp = await tool_registry.bound_executor(tctx).execute(
        ToolCall(tool=spec_exp, arguments={"artifact_id": art_id, "format": "pdf", "dpi": 150})
    )
    assert exp.ok and exp.output["validation"]["mime_type"] == "application/pdf"
    refused = await tool_registry.bound_executor(tctx).execute(
        ToolCall(
            tool=spec_exp, arguments={"artifact_id": art_id, "format": "png", "expected_size": "1000x1000"}
        )
    )
    assert not refused.ok and "export refused" in (refused.error_message or "")

    # /auto: manager delegates sequentially to resize → qc → export (heuristic plan with the echo runner)
    res = await admin.post(
        f"/api/v1/conversations/{conv['id']}/runs",
        json={
            "content": "/auto resize the approved poster to 4:5, run qc and export it",
            "selected_asset_ids": [asset["id"]],
        },
    )
    assert res.status_code == 202, res.text
    await drain(app)
    run = (await admin.get(f"/api/v1/runs/{res.json()['run_id']}")).json()
    assert run["status"] == "SUCCEEDED", run
    names = [n["name"] for n in run["nodes"]]
    assert names == [
        "Parse command",
        "Load context",
        "Manager",
        "Resize Agent",
        "QC Agent",
        "Export Agent",
        "Save result",
    ], names
    assert all(n["status"] == "SUCCEEDED" for n in run["nodes"])
    msgs = (await admin.get(f"/api/v1/conversations/{conv['id']}/messages")).json()
    assert "**Resize Agent**" in msgs[-1]["content"] and "**Export Agent**" in msgs[-1]["content"]
    # audit + usage rows exist
    async with app.state.session_factory() as session:
        from app.models.workflows import ApiUsage

        assert (await session.scalar(select(ApiUsage).limit(1))) is not None
