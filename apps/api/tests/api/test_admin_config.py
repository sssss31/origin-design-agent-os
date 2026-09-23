"""Phase 2 acceptance: admin adds a provider key, creates a skill and an agent, attaches
skill/tool/handoff, publishes, and the /command appears for members without a redeploy."""

from __future__ import annotations

import pytest
from app.domain.roles import Role
from app.models.governance import AuditLog, SecretRef
from sqlalchemy import select

from tests.conftest import requires_db

pytestmark = requires_db

BASE = "/api/v1/admin"


async def _provider(admin, ptype: str = "echo", name: str = "Echo Provider"):  # type: ignore[no-untyped-def]
    res = await admin.post(f"{BASE}/providers", json={"name": name, "type": ptype})
    assert res.status_code == 201, res.text
    return res.json()


async def test_provider_secret_is_write_only_and_encrypted(app, make_user, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    admin = await make_user("admin@example.com", role=Role.ADMIN)
    provider = await _provider(admin, "openai", "OpenAI Production")
    assert provider["has_secret"] is False and provider["base_url"] == "https://api.openai.com/v1"

    res = await admin.post(
        f"{BASE}/providers/{provider['id']}/secret", json={"api_key": "sk-test-1234567890abcdef"}
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["has_secret"] is True and body["secret_fingerprint"].startswith("…")
    assert body["configured"] is True and body["key_preview"] == "sk-••••••••cdef"
    assert body["environment"] == "production"
    assert "sk-test" not in res.text and "api_key" not in body

    # spec §2/§3 contracts by provider type: masked preview only, sanitized connection result
    status_res = await admin.get(f"{BASE}/providers/openai/status")
    assert status_res.status_code == 200, status_res.text
    st = status_res.json()
    assert st == {**st, "provider": "openai", "configured": True, "key_preview": "sk-••••••••cdef"}
    assert "sk-test-1234567890abcdef" not in status_res.text

    async with app.state.session_factory() as session:
        ref = (await session.scalars(select(SecretRef))).one()
        assert ref.ciphertext and "sk-test" not in ref.ciphertext
        assert ref.backend == "fernet"

    # rotation bumps the secret version, never echoes the value
    res = await admin.post(
        f"{BASE}/providers/{provider['id']}/secret", json={"api_key": "sk-test-rotated-0000000000"}
    )
    assert res.status_code == 200
    async with app.state.session_factory() as session:
        ref = (await session.scalars(select(SecretRef))).one()
        assert ref.version == 2

    # connection test uses the stored key, returns status metadata only
    from app.services import providers as providers_module

    seen: dict[str, str | None] = {}

    async def fake_probe(provider_type: str, base_url: str | None, api_key: str | None):  # type: ignore[no-untyped-def]
        seen["key"] = api_key
        return providers_module.ProbeResult(
            ok=True, message="authenticated; 3 models visible", models=["gpt-a", "gpt-b", "gpt-vision"]
        )

    monkeypatch.setattr(providers_module, "probe_provider", fake_probe)
    res = await admin.post(f"{BASE}/providers/{provider['id']}/test")
    assert res.status_code == 200, res.text
    assert res.json()["ok"] is True and res.json()["available_models"] == ["gpt-a", "gpt-b", "gpt-vision"]
    assert seen["key"] == "sk-test-rotated-0000000000"
    assert "sk-test" not in res.text
    by_type = await admin.post(f"{BASE}/providers/openai/test")
    assert by_type.status_code == 200, by_type.text
    assert (
        by_type.json()["success"] is True
        and by_type.json()["status"] == "connected"
        and by_type.json()["provider"] == "openai"
    )
    assert "sk-test" not in by_type.text

    got = await admin.get(f"{BASE}/providers/{provider['id']}")
    assert got.json()["health_status"] == "ok" and got.json()["last_tested_at"]

    # allowlist + default model
    res = await admin.put(
        f"{BASE}/providers/{provider['id']}/models",
        json={
            "models": [{"model": "gpt-a"}, {"model": "gpt-vision", "capabilities": {"vision": True}}],
            "default_model": "gpt-a",
        },
    )
    assert res.status_code == 200, res.text
    assert [m["model"] for m in res.json()["models"]] == ["gpt-a", "gpt-vision"] and res.json()[
        "default_model"
    ] == "gpt-a"
    bad = await admin.put(
        f"{BASE}/providers/{provider['id']}/models",
        json={"models": [{"model": "gpt-a"}], "default_model": "gpt-z"},
    )
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "default_not_allowed"


async def test_full_admin_flow_publish_rollback_and_commands(app, make_user) -> None:  # type: ignore[no-untyped-def]
    admin = await make_user("admin@example.com", role=Role.ADMIN)
    member = await make_user("member@example.com", role=Role.MEMBER)
    provider = await _provider(admin)
    await admin.put(
        f"{BASE}/providers/{provider['id']}/models",
        json={"models": [{"model": "echo-1"}], "default_model": "echo-1"},
    )

    # --- skill: draft → publish
    res = await admin.post(
        f"{BASE}/skills",
        json={
            "name": "Brand & Asset Lock",
            "description": "Preserve logos",
            "version": {
                "instructions": "Keep the logo {{position}}.",
                "variables_defaults": {"position": "top-left"},
                "default_priority": 10,
            },
        },
    )
    assert res.status_code == 201, res.text
    skill = res.json()
    assert (
        skill["status"] == "draft"
        and skill["draft_version"]["version"] == 1
        and skill["active_version"] is None
    )
    res = await admin.post(f"{BASE}/skills/{skill['id']}/publish", json={})
    assert res.status_code == 200, res.text
    skill = res.json()
    assert (
        skill["status"] == "active"
        and skill["active_version"]["version"] == 1
        and skill["draft_version"] is None
    )

    # editing an active skill creates a draft; active stays untouched until publish
    res = await admin.post(
        f"{BASE}/skills/{skill['id']}/versions",
        json={"instructions": "Keep the logo {{position}} and colors."},
    )
    skill = res.json()
    assert (
        skill["draft_version"]["version"] == 2
        and skill["active_version"]["instructions"] == "Keep the logo {{position}}."
    )

    # --- tool
    res = await admin.post(
        f"{BASE}/tools",
        json={
            "slug": "image.inspect",
            "display_name": "Inspect image",
            "executor_type": "http_api",
            "config": {"url": "https://tools.internal/inspect"},
            "input_schema": {"type": "object", "properties": {"asset_id": {"type": "string"}}},
        },
    )
    assert res.status_code == 201, res.text
    tool = res.json()
    assert tool["active_version"]["version"] == 1
    res = await admin.patch(
        f"{BASE}/tools/{tool['id']}", json={"timeout_seconds": 120, "change_note": "slower endpoint"}
    )
    assert (
        res.json()["active_version"]["version"] == 2
        and res.json()["active_version"]["timeout_seconds"] == 120
    )
    res = await admin.post(
        f"{BASE}/tools/{tool['id']}/permissions",
        json={"subject_type": "role", "subject_key": "member", "allowed": True},
    )
    assert res.status_code == 200 and res.json()["permissions"][0]["subject_key"] == "member"

    # --- agent: create draft, publish must fail until configured
    res = await admin.post(
        f"{BASE}/agents",
        json={
            "name": "Copy Agent",
            "command": "Copy",
            "description": "Writes copy",
            "version": {"instructions": "You write on-brand copy."},
        },
    )
    assert res.status_code == 201, res.text
    agent = res.json()
    assert (
        agent["command"] == "/copy" and agent["status"] == "draft" and agent["draft_version"]["version"] == 1
    )
    res = await admin.post(f"{BASE}/agents/{agent['id']}/publish", json={})
    assert res.status_code == 422 and res.json()["error"]["code"] == "publish_validation_failed"
    assert any("provider is required" in p for p in res.json()["error"]["details"])

    # no command visible to members yet
    assert (await member.get("/api/v1/agents/commands")).json() == []

    # configure draft, attach skill (pinned to v1) + tool + handoff, then publish
    res = await admin.post(
        f"{BASE}/agents/{agent['id']}/versions", json={"provider_id": provider["id"], "model": "echo-9"}
    )
    assert res.status_code == 200
    res = await admin.post(f"{BASE}/agents/{agent['id']}/publish", json={})
    assert res.status_code == 422 and any("allowlist" in p for p in res.json()["error"]["details"])
    await admin.post(f"{BASE}/agents/{agent['id']}/versions", json={"model": "echo-1"})
    res = await admin.post(
        f"{BASE}/agents/{agent['id']}/skills/{skill['id']}",
        json={
            "priority": 5,
            "skill_version_id": skill["active_version"]["id"],
            "variables": {"position": "bottom-right"},
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["draft_version"]["skills"][0]["skill_slug"] == "brand-asset-lock"
    res = await admin.post(f"{BASE}/agents/{agent['id']}/tools/{tool['id']}", json={"max_calls_per_run": 3})
    assert res.json()["draft_version"]["tools"][0]["tool_slug"] == "image.inspect"
    res = await admin.post(
        f"{BASE}/agents",
        json={
            "name": "QC Agent",
            "command": "/qc",
            "version": {
                "instructions": "You check designs.",
                "provider_id": provider["id"],
                "model": "echo-1",
            },
        },
    )
    qc = res.json()
    res = await admin.post(
        f"{BASE}/agents/{agent['id']}/handoffs/{qc['id']}",
        json={"routing_hint": "after copy is final", "is_failure_route": False},
    )
    assert res.json()["draft_version"]["handoffs"][0]["target_agent_command"] == "/qc"

    res = await admin.post(f"{BASE}/agents/{agent['id']}/publish", json={"change_note": "initial"})
    assert res.status_code == 200, res.text
    agent = res.json()
    assert (
        agent["status"] == "active"
        and agent["active_version"]["version"] == 1
        and agent["draft_version"] is None
    )
    assert agent["active_version"]["change_note"] == "initial"

    # command is live for members immediately (no redeploy)
    cmds = await member.get("/api/v1/agents/commands")
    assert [c["command"] for c in cmds.json()] == ["/copy"]
    assert cmds.json()[0]["description"] == "Writes copy"

    # sandbox test runs through the echo runner with composed instructions + bound tools
    res = await admin.post(
        f"{BASE}/agents/{agent['id']}/test", json={"input": "Write a tagline !image.inspect"}
    )
    assert res.status_code == 200, res.text
    trace = res.json()
    assert trace["runner"] == "echo" and trace["model"] == "echo-1" and trace["tools"] == ["image.inspect"]
    assert trace["instruction_sections"] == [
        "platform_rules",
        "agent_instructions",
        "skill:brand-asset-lock@1",
    ]
    assert "image.inspect→True" in trace["output_text"]
    assert "reasoning" not in trace

    # clarification path is reported, not hidden
    res = await admin.post(f"{BASE}/agents/{agent['id']}/test", json={"input": "resize ?clarify"})
    assert res.json()["requires_clarification"] is True and res.json()["question"]

    # editing after publish creates v2 draft with copied bindings; active stays v1
    res = await admin.post(
        f"{BASE}/agents/{agent['id']}/versions", json={"instructions": "You write bold on-brand copy."}
    )
    agent = res.json()
    assert agent["draft_version"]["version"] == 2 and agent["active_version"]["version"] == 1
    assert (
        agent["draft_version"]["skills"][0]["priority"] == 5
        and agent["draft_version"]["tools"][0]["max_calls_per_run"] == 3
    )
    assert agent["active_version"]["instructions"] == "You write on-brand copy."
    res = await admin.post(f"{BASE}/agents/{agent['id']}/publish", json={})
    agent = res.json()
    assert agent["active_version"]["version"] == 2

    # rollback to v1 by selecting it as active
    v1 = next(v for v in agent["versions"] if v["version"] == 1)
    res = await admin.post(f"{BASE}/agents/{agent['id']}/publish", json={"version_id": v1["id"]})
    assert res.status_code == 200, res.text
    assert (
        res.json()["active_version"]["version"] == 1
        and res.json()["active_version"]["instructions"] == "You write on-brand copy."
    )

    # command uniqueness among active agents
    res = await admin.post(
        f"{BASE}/agents",
        json={
            "name": "Copy Two",
            "command": "/copy",
            "version": {"instructions": "x", "provider_id": provider["id"], "model": "echo-1"},
        },
    )
    dup = await admin.post(f"{BASE}/agents/{res.json()['id']}/publish", json={})
    assert dup.status_code == 422 and any("/copy" in p for p in dup.json()["error"]["details"])

    # disable → command disappears; re-enable → back
    res = await admin.patch(f"{BASE}/agents/{agent['id']}", json={"status": "disabled"})
    assert res.json()["status"] == "disabled"
    assert (await member.get("/api/v1/agents/commands")).json() == []
    res = await admin.patch(f"{BASE}/agents/{agent['id']}", json={"status": "active"})
    assert [c["command"] for c in (await member.get("/api/v1/agents/commands")).json()] == ["/copy"]

    # audit trail covers publishes, secret-free
    async with app.state.session_factory() as session:
        actions = [
            a.action for a in (await session.scalars(select(AuditLog).order_by(AuditLog.created_at))).all()
        ]
    for expected in (
        "provider.created",
        "skill.published",
        "skill.draft_saved",
        "tool.created",
        "tool.updated",
        "tool.permission_set",
        "agent.created",
        "agent.skill_attached",
        "agent.tool_attached",
        "agent.handoff_set",
        "agent.published",
        "agent.tested",
        "agent.rolled_back",
        "agent.disabled",
        "agent.enabled",
    ):
        assert expected in actions, expected


async def test_skill_file_upload_and_validation(app, make_user) -> None:  # type: ignore[no-untyped-def]
    admin = await make_user("admin@example.com", role=Role.ADMIN)
    res = await admin.post(
        f"{BASE}/skills",
        json={
            "name": "Print Preflight",
            "version": {"instructions": "Check bleed.", "tool_requirements": ["pdf.inspect"]},
        },
    )
    skill = res.json()
    res = await admin.post(f"{BASE}/skills/{skill['id']}/publish", json={})
    assert res.status_code == 422 and "pdf.inspect" in str(res.json()["error"]["details"])
    res = await admin.client.post(
        f"{BASE}/skills/{skill['id']}/files",
        headers=admin.headers,
        files={"file": ("bleed-guide.md", b"# Bleed\n3mm on all sides", "text/markdown")},
        data={"description": "House bleed rules"},
    )
    assert res.status_code == 201, res.text
    files = res.json()["draft_version"]["files"]
    assert files[0]["filename"] == "bleed-guide.md" and files[0]["size_bytes"] == 24
    bad = await admin.client.post(
        f"{BASE}/skills/{skill['id']}/files",
        headers=admin.headers,
        files={"file": ("x.exe", b"MZ", "application/x-msdownload")},
    )
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "unsupported_file_type"


async def test_admin_endpoints_require_admin_and_are_tenant_scoped(make_user) -> None:  # type: ignore[no-untyped-def]
    member = await make_user("member@example.com", role=Role.MEMBER)
    res = await member.get(f"{BASE}/agents")
    assert res.status_code == 403 and res.json()["error"]["code"] == "insufficient_role"
    acme = await make_user("acme@example.com", org="Acme", role=Role.ADMIN)
    globex = await make_user("globex@example.com", org="Globex", role=Role.ADMIN)
    provider = await _provider(acme)
    agent = (
        await acme.post(
            f"{BASE}/agents",
            json={
                "name": "A",
                "command": "/a",
                "version": {"instructions": "x", "provider_id": provider["id"], "model": "echo-1"},
            },
        )
    ).json()
    assert (await globex.get(f"{BASE}/agents/{agent['id']}")).status_code == 404
    assert (await globex.get(f"{BASE}/providers/{provider['id']}")).status_code == 404
    assert (await globex.get(f"{BASE}/agents")).json() == []
    # cross-org provider cannot be referenced from another org's draft
    other = (await globex.post(f"{BASE}/agents", json={"name": "B", "command": "/b"})).json()
    res = await globex.post(f"{BASE}/agents/{other['id']}/versions", json={"provider_id": provider["id"]})
    assert res.status_code == 404


@pytest.mark.parametrize("command", ["no-slash-space x", "/9bad", "/Bad Command"])
async def test_agent_command_validation(make_user, command: str) -> None:  # type: ignore[no-untyped-def]
    admin = await make_user("admin@example.com", role=Role.ADMIN)
    res = await admin.post(f"{BASE}/agents", json={"name": "X", "command": command})
    assert res.status_code == 422


async def test_provider_delete_refused_while_in_use_and_secret_removal(app, make_user) -> None:  # type: ignore[no-untyped-def]
    from app.models.governance import SecretRef
    from sqlalchemy import select

    admin = await make_user("admin@example.com", role=Role.ADMIN)
    provider = await _provider(admin, "openai", "OpenAI Production")
    await admin.post(
        f"{BASE}/providers/{provider['id']}/secret", json={"api_key": "sk-proj-abcdefghijklmnop7Xk2"}
    )
    agent = (
        await admin.post(
            f"{BASE}/agents",
            json={
                "name": "Master",
                "command": "/master",
                "version": {"instructions": "x", "provider_id": provider["id"], "model": "gpt-5"},
            },
        )
    ).json()
    refused = await admin.delete(f"{BASE}/providers/{provider['id']}")
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "provider_in_use"
    assert "Master" in refused.json()["error"]["details"]
    # removing the credential keeps the provider but drops the ciphertext
    res = await admin.delete(f"{BASE}/providers/{provider['id']}/secret")
    assert res.status_code == 200 and res.json()["configured"] is False and res.json()["key_preview"] is None
    async with app.state.session_factory() as session:
        assert (await session.scalars(select(SecretRef))).all() == []
    # detach the agent's draft from the provider, then delete works
    await admin.post(f"{BASE}/agents/{agent['id']}/versions", json={"provider_id": None})
    assert (await admin.delete(f"{BASE}/providers/{provider['id']}")).status_code == 204
    assert (await admin.get(f"{BASE}/providers/openai/status")).json()["configured"] is False
    # non-admins cannot reach any provider endpoint
    member = await make_user("m@example.com", role=Role.MEMBER)
    assert (await member.get(f"{BASE}/providers/openai/status")).status_code == 403


async def test_integrations_overview_cards(make_user) -> None:  # type: ignore[no-untyped-def]
    admin = await make_user("admin@example.com", role=Role.ADMIN)
    provider = await _provider(admin, "openai", "OpenAI Production")
    await admin.post(f"{BASE}/providers/{provider['id']}/secret", json={"api_key": "sk-proj-abcdefghijklmnop7Xk2"})
    await admin.put(f"{BASE}/providers/{provider['id']}/models", json={"models": [{"model": "gpt-5"}], "default_model": "gpt-5"})
    agent = (await admin.post(f"{BASE}/agents", json={"name": "Master Design Agent", "command": "/master", "version": {"instructions": "x", "provider_id": provider["id"], "model": "gpt-5"}})).json()
    await admin.post(f"{BASE}/agents/{agent['id']}/publish", json={})
    res = await admin.get(f"{BASE}/integrations/overview")
    assert res.status_code == 200, res.text
    body = res.json()
    assert {t["type"] for t in body["provider_types"]} == {"openai", "echo"}
    card = next(c for c in body["providers"] if c["provider"]["id"] == provider["id"])
    assert card["used_by"] == ["Master Design Agent"] and card["provider"]["key_preview"] == "sk-proj-••••••••7Xk2"
    assert card["provider"]["models"][0]["resolved_capabilities"]["supports_reasoning"] is True
    assert "abcdefghijklmnop" not in res.text
    models = await admin.get(f"{BASE}/providers/{provider['id']}/supported-models")
    assert models.status_code == 200 and any(m["model"] == "gpt-5" for m in models.json())
