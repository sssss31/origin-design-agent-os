"""SERVERLESS=true (Vercel Functions): no lifespan, no background work — a queued run is executed
inside the SSE request that streams it, and startup happens lazily on the first request."""

from __future__ import annotations

import asyncio
from typing import Any

from app.core.config import Settings
from app.domain.roles import Role
from httpx import ASGITransport, AsyncClient

from tests.api.test_runs import setup_org
from tests.api.test_workspace_v0 import _agent_transport
from tests.conftest import requires_db

pytestmark = requires_db
ADMIN = "/api/v1/admin"


async def test_run_executes_inside_the_event_stream(app, make_user, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import app.core.ssrf as ssrf
    from app.main import create_app

    monkeypatch.setattr(ssrf, "resolve_host", lambda host: ["93.184.216.34"])
    admin = await make_user("serverless@example.com", role=Role.ADMIN)
    _provider, _ws, project = await setup_org(admin)
    assert (
        await admin.post(f"{ADMIN}/seed/agent-registry", json={"connection_type": "http"})
    ).status_code == 200
    agents = {a["command"]: a for a in (await admin.get(f"{ADMIN}/agents")).json()}
    res = await admin.put(
        f"{ADMIN}/agents/{agents['/qc']['id']}/connection",
        json={
            "connection_type": "http",
            "api_endpoint": "https://agents.example.com/qc/run",
            "api_key": "qc-key-ABCDEF7890",
            "config": {"response_text_path": "reply"},
        },
    )
    assert res.status_code == 200, res.text

    # A second app instance in serverless mode, deliberately started WITHOUT the ASGI lifespan.
    serverless_app = create_app(Settings(serverless=True, _env_file=None))
    assert not getattr(serverless_app.state, "ready", False)
    async with AsyncClient(
        transport=ASGITransport(app=serverless_app), base_url="http://testserver"
    ) as client:
        assert (await client.get("/healthz")).status_code == 200  # lazy startup (migrations + adapters)
        assert serverless_app.state.ready and serverless_app.state.adapters.queue.name == "deferred"
        calls: list[dict[str, Any]] = []
        serverless_app.state.adapters.http_transport = _agent_transport(calls)
        login = await client.post(
            "/api/v1/auth/login", json={"email": "serverless@example.com", "password": "Password123!"}
        )
        assert login.status_code == 200, login.text
        headers = {
            "Authorization": f"Bearer {login.json()['access_token']}",
            "X-Organization-Id": admin.organization_id,
        }

        conv = (
            await client.post(
                f"/api/v1/projects/{project['id']}/conversations", json={"title": "s"}, headers=headers
            )
        ).json()
        created = await client.post(
            f"/api/v1/conversations/{conv['id']}/runs", json={"content": "/qc check"}, headers=headers
        )
        assert created.status_code == 202, created.text
        run_id = created.json()["run_id"]
        # nothing ran in the background: the run is still queued
        assert (await client.get(f"/api/v1/runs/{run_id}", headers=headers)).json()["status"] == "QUEUED"

        # opening the event stream executes the run in-process and streams it to completion
        stream = await asyncio.wait_for(
            client.get(f"/api/v1/runs/{run_id}/events", headers=headers), timeout=60
        )
        assert stream.status_code == 200
        assert "event: run.completed" in stream.text and "event: response.streaming" in stream.text
        assert calls and calls[-1]["path"] == "/qc/run"
        run = (await client.get(f"/api/v1/runs/{run_id}", headers=headers)).json()
        assert run["status"] == "SUCCEEDED", run["error_json"]
        messages = (await client.get(f"/api/v1/conversations/{conv['id']}/messages", headers=headers)).json()
        assert messages[-1]["role"] == "assistant" and "check" in messages[-1]["content"]
        # a second subscription just replays history and ends
        again = await asyncio.wait_for(
            client.get(f"/api/v1/runs/{run_id}/events", headers=headers), timeout=30
        )
        assert "event: run.completed" in again.text
    await serverless_app.state.engine.dispose()
