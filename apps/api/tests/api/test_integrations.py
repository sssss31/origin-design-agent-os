"""Custom REST integrations: cURL import → encrypted secrets → auto tool → agent run via HTTP executor."""

from __future__ import annotations

import json
from typing import Any

import httpx
from app.domain.roles import Role
from app.models.governance import SecretRef
from sqlalchemy import select

from tests.api.test_runs import drain, make_agent, setup_org
from tests.conftest import requires_db

pytestmark = requires_db
ADMIN = "/api/v1/admin"

CURL = """curl https://svg.example.com/v1/generate \\
  -H "Authorization: Bearer svg-live-key-ABCDEFGH1234" \\
  -H "Content-Type: application/json" \\
  -d '{"prompt": "{{prompt}}", "workspace_id": "{{workspace_id}}", "asset_url": "{{asset_url}}"}'"""


def _mock_transport(calls: list[dict[str, Any]]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode() if request.content else ""
        calls.append(
            {
                "url": str(request.url),
                "auth": request.headers.get("authorization"),
                "body": body,
                "method": request.method,
            }
        )
        if request.url.path.endswith("/svg"):
            return httpx.Response(
                200,
                content=b"<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10'/>",
                headers={"content-type": "image/svg+xml"},
            )
        if request.url.path.endswith("/fail"):
            return httpx.Response(503, json={"error": "down"})
        return httpx.Response(200, json={"ok": True, "echo": json.loads(body) if body else None})

    return httpx.MockTransport(handler)


async def test_curl_import_extracts_secret_and_creates_tool(app, make_user, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import app.core.ssrf as ssrf

    monkeypatch.setattr(ssrf, "resolve_host", lambda host: ["93.184.216.34"])
    admin = await make_user("admin@example.com", role=Role.ADMIN)
    # dry run never stores anything and masks the secret
    preview = await admin.post(f"{ADMIN}/integrations/parse-curl", json={"curl": CURL})
    assert preview.status_code == 200, preview.text
    pv = preview.json()
    assert pv["summary"] == {
        "method": "POST",
        "endpoint": "/v1/generate",
        "host": "svg.example.com",
        "auth": "Secret configured",
        "body": "JSON",
        "status": "Ready",
    }
    assert pv["secrets"][0]["name"] == "api_key" and "ABCDEFGH1234" not in preview.text
    assert pv["variables"] == ["prompt", "workspace_id", "asset_url"]

    res = await admin.post(
        f"{ADMIN}/integrations/import-curl", json={"curl": CURL, "name": "Internal SVG Engine"}
    )
    assert res.status_code == 201, res.text
    integ = res.json()
    assert integ["headers_template"]["Authorization"] == "Bearer {{secrets.api_key}}"
    assert integ["secrets"][0]["name"] == "api_key" and integ["secrets"][0]["key_preview"].endswith("1234")
    assert integ["auth_summary"] == "header" and integ["missing_secrets"] == []
    assert integ["tool_slug"] == "api.internal_svg_engine" and integ["variables"] == [
        "prompt",
        "workspace_id",
        "asset_url",
    ]
    assert "svg-live-key" not in res.text
    async with app.state.session_factory() as session:
        refs = (await session.scalars(select(SecretRef))).all()
        assert len(refs) == 1 and "svg-live-key" not in (refs[0].ciphertext or "")
    # audit row must not carry the credential either
    audit = (await admin.get(f"{ADMIN}/audit?action=integration")).json()
    assert audit and "svg-live-key" not in json.dumps(audit)

    # the auto-created tool is a normal editable tool row bound to the integration
    tools = {t["slug"]: t for t in (await admin.get(f"{ADMIN}/tools")).json()}
    tool = tools["api.internal_svg_engine"]
    assert (
        tool["executor_type"] == "http_api"
        and tool["active_version"]["config"]["integration_id"] == integ["id"]
    )
    assert set(tool["active_version"]["input_schema"]["properties"]) == {
        "prompt",
        "workspace_id",
        "asset_url",
    }

    # Test API: request → api → response with masked credential, status, latency, size
    calls: list[dict[str, Any]] = []
    app.state.adapters.http_transport = _mock_transport(calls)
    try:
        res = await admin.post(
            f"{ADMIN}/integrations/{integ['id']}/test",
            json={"variables": {"prompt": 'Test "design"', "workspace_id": "demo"}},
        )
        assert res.status_code == 200, res.text
        out = res.json()
        assert (
            out["ok"] and out["status"] == 200 and out["latency_ms"] >= 0 and out["response_size_bytes"] > 0
        )
        assert out["request"]["headers"]["Authorization"] == "Bearer ••••••••"
        assert out["response_preview"]["echo"]["prompt"] == 'Test "design"'
        assert "svg-live-key" not in res.text
        assert (
            calls[0]["auth"] == "Bearer svg-live-key-ABCDEFGH1234"
            and json.loads(calls[0]["body"])["workspace_id"] == "demo"
        )
        got = (await admin.get(f"{ADMIN}/integrations/{integ['id']}")).json()
        assert (
            got["health_status"] == "ok" and got["request_count"] == 1 and got["avg_latency_ms"] is not None
        )
    finally:
        app.state.adapters.http_transport = None

    # SSRF: a private endpoint is refused at save time
    bad = await admin.patch(
        f"{ADMIN}/integrations/{integ['id']}", json={"endpoint": "https://169.254.169.254/latest"}
    )
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "outbound_blocked"
    # rotate + delete secret
    res = await admin.post(
        f"{ADMIN}/integrations/{integ['id']}/secrets",
        json={"name": "api_key", "value": "svg-live-key-ROTATED9999"},
    )
    assert res.json()["secrets"][0]["key_preview"].endswith("9999") and res.json()["secrets"][0]["rotated_at"]
    res = await admin.delete(f"{ADMIN}/integrations/{integ['id']}/secrets/api_key")
    assert res.json()["secrets"] == [] and res.json()["missing_secrets"] == ["api_key"]
    member = await make_user("m@example.com", role=Role.MEMBER)
    assert (await member.get(f"{ADMIN}/integrations")).status_code == 403


async def test_agent_calls_custom_api_tool_and_stores_file_artifact(app, make_user, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import app.core.ssrf as ssrf

    monkeypatch.setattr(ssrf, "resolve_host", lambda host: ["93.184.216.34"])
    admin = await make_user("admin@example.com", role=Role.ADMIN)
    provider, ws, project = await setup_org(admin)
    integ = (
        await admin.post(
            f"{ADMIN}/integrations",
            json={
                "name": "SVG Engine",
                "method": "POST",
                "endpoint": "https://svg.example.com/v1/svg",
                "headers_template": {"X-Api-Key": "{{secrets.svg_key}}"},
                "body_template": '{"prompt": "{{prompt}}", "workspace_id": "{{workspace_id}}"}',
                "secrets": [{"name": "svg_key", "value": "K-1234567890", "location": "header"}],
            },
        )
    ).json()
    tools = {t["slug"]: t for t in (await admin.get(f"{ADMIN}/tools")).json()}
    editable = await make_agent(
        admin, provider, name="Editable Agent", command="/editable", tool_ids=[tools["api.svg_engine"]["id"]]
    )
    # the integration card shows the assignment (API → Agent)
    listing = (await admin.get(f"{ADMIN}/integrations")).json()
    assert listing[0]["used_by"] == ["Editable Agent"]
    overview = (await admin.get(f"{ADMIN}/integrations/overview")).json()
    assert overview["custom"][0]["tool_slug"] == "api.svg_engine"

    calls: list[dict[str, Any]] = []
    app.state.adapters.http_transport = _mock_transport(calls)
    try:
        conv = (await admin.post(f"/api/v1/projects/{project['id']}/conversations", json={})).json()
        created = (
            await admin.post(
                f"/api/v1/conversations/{conv['id']}/runs",
                json={"content": "/editable make it editable !api.svg_engine"},
            )
        ).json()
        await drain(app)
        run = (await admin.get(f"/api/v1/runs/{created['run_id']}")).json()
        assert run["status"] == "SUCCEEDED", run
        assert calls and calls[0]["auth"] is None and calls[0]["method"] == "POST"
        history = (await admin.get(f"/api/v1/runs/{created['run_id']}/events/history")).json()
        types = [e["type"] for e in history]
        assert "tool.started" in types and "artifact.created" in types
        assert "K-1234567890" not in json.dumps(history)
        artifacts = (await admin.get(f"/api/v1/projects/{project['id']}/artifacts")).json()
        assert any(a["type"] == "svg" for a in artifacts)
    finally:
        app.state.adapters.http_transport = None
    # used integration cannot be deleted while bound; after detaching it can
    assert (await admin.delete(f"{ADMIN}/integrations/{integ['id']}")).status_code == 409
    await admin.delete(f"{ADMIN}/agents/{editable['id']}/tools/{tools['api.svg_engine']['id']}")
    await admin.post(f"{ADMIN}/agents/{editable['id']}/publish", json={})
    assert (await admin.delete(f"{ADMIN}/integrations/{integ['id']}")).status_code == 204
    assert "api.svg_engine" not in {t["slug"] for t in (await admin.get(f"{ADMIN}/tools")).json()}
