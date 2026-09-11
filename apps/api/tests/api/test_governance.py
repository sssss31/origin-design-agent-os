from app.domain.roles import Role

from tests.conftest import requires_db

pytestmark = requires_db


async def test_audit_and_usage_endpoints(make_user) -> None:  # type: ignore[no-untyped-def]
    admin = await make_user("admin@example.com", role=Role.ADMIN)
    await admin.post("/api/v1/workspaces", json={"name": "Audited"})
    rows = (await admin.get("/api/v1/admin/audit")).json()
    assert rows[0]["action"] == "workspace.created" and rows[0]["actor_email"] == "admin@example.com"
    filtered = (await admin.get("/api/v1/admin/audit", params={"action": "workspace."})).json()
    assert all(r["action"].startswith("workspace.") for r in filtered)
    usage = (await admin.get("/api/v1/admin/usage")).json()
    assert usage["runs_today"] == 0 and usage["error_rate"] == 0.0
    member = await make_user("m@example.com")
    assert (await member.get("/api/v1/admin/audit")).status_code == 403


async def test_seed_design_agents_from_console(make_user) -> None:  # type: ignore[no-untyped-def]
    admin = await make_user("admin@example.com", role=Role.ADMIN)
    res = await admin.post("/api/v1/admin/seed/design-agents", json={"provider_type": "echo"})
    assert res.status_code == 200, res.text
    stats = res.json()
    assert stats["agents"] == 8 and stats["published"] == 8 and stats["skills"] == 8 and stats["tools"] >= 9
    cmds = {c["command"] for c in (await admin.get("/api/v1/agents/commands")).json()}
    assert cmds == {"/master", "/resize", "/editable", "/qc", "/copy", "/asset", "/export", "/auto"}
    # idempotent
    again = (await admin.post("/api/v1/admin/seed/design-agents", json={"provider_type": "echo"})).json()
    assert again["agents"] == 0 and again["tools"] == 0


async def test_seed_keeps_an_admins_existing_command(make_user) -> None:  # type: ignore[no-untyped-def]
    admin = await make_user("admin2@example.com", role=Role.ADMIN)
    provider = (await admin.post("/api/v1/admin/providers", json={"name": "Echo", "type": "echo"})).json()
    await admin.put(
        f"/api/v1/admin/providers/{provider['id']}/models",
        json={"models": [{"model": "echo-1"}], "default_model": "echo-1"},
    )
    mine = (
        await admin.post(
            "/api/v1/admin/agents",
            json={
                "name": "My Copywriter",
                "command": "/copy",
                "version": {"instructions": "mine", "provider_id": provider["id"], "model": "echo-1"},
            },
        )
    ).json()
    assert (await admin.post(f"/api/v1/admin/agents/{mine['id']}/publish", json={})).status_code == 200
    res = await admin.post("/api/v1/admin/seed/design-agents", json={"provider_type": "echo"})
    assert res.status_code == 200, res.text
    assert res.json()["agents"] == 7 and res.json()["skipped"] == 1
    cmds = {c["command"]: c["name"] for c in (await admin.get("/api/v1/agents/commands")).json()}
    assert cmds["/copy"] == "My Copywriter" and len(cmds) == 8
    agents = (await admin.get("/api/v1/admin/agents")).json()
    manager = next(a for a in agents if a["command"] == "/auto")
    detail = (await admin.get(f"/api/v1/admin/agents/{manager['id']}")).json()
    assert manager["is_manager"] and len(detail["active_version"]["handoffs"]) == 7
    resize = next(a for a in agents if a["command"] == "/resize")
    detail = (await admin.get(f"/api/v1/admin/agents/{resize['id']}")).json()
    assert {s["skill_slug"] for s in detail["active_version"]["skills"]} >= {
        "brand-asset-lock",
        "design-adaptation",
    }
    assert {t["tool_slug"] for t in detail["active_version"]["tools"]} >= {"image.resize", "image.inspect"}


async def test_rate_limit_headers(client, make_user, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from app.core.ratelimit import RateLimiter

    limiter = RateLimiter.__new__(RateLimiter)
    limiter.limit, limiter.window, limiter._local, limiter._redis = 3, 60.0, {}, None
    for _ in range(3):
        assert (await limiter.check("k"))[0] is True
    allowed, retry = await limiter.check("k")
    assert allowed is False and retry >= 1
