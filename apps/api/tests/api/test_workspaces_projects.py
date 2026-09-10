from app.domain.roles import Role

from tests.conftest import requires_db

pytestmark = requires_db


async def test_member_creates_workspace_and_project(client, make_user) -> None:  # type: ignore[no-untyped-def]
    actor = await make_user("dana@example.com")
    res = await actor.post(
        "/api/v1/workspaces", json={"name": "Brand Studio", "rules_text": "Use brand blue."}
    )
    assert res.status_code == 201, res.text
    ws = res.json()
    assert ws["slug"] == "brand-studio" and ws["my_role"] == "admin"
    assert (await actor.get("/api/v1/workspaces")).json()[0]["id"] == ws["id"]

    dup = await actor.post("/api/v1/workspaces", json={"name": "Brand Studio"})
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "slug_taken"

    res = await actor.post(f"/api/v1/workspaces/{ws['id']}/projects", json={"name": "Autumn Campaign"})
    assert res.status_code == 201, res.text
    project = res.json()
    assert project["slug"] == "autumn-campaign"
    got = await actor.get(f"/api/v1/projects/{project['id']}")
    assert got.status_code == 200 and got.json()["workspace_id"] == ws["id"]

    upd = await actor.patch(
        f"/api/v1/projects/{project['id']}", json={"summary_text": "Poster set for autumn."}
    )
    assert upd.status_code == 200 and upd.json()["summary_text"] == "Poster set for autumn."

    rule = await actor.post(
        f"/api/v1/projects/{project['id']}/rules",
        json={"name": "Margins", "rule_text": "Keep 24px safe margin.", "priority": 10},
    )
    assert rule.status_code == 201
    rules = await actor.get(f"/api/v1/projects/{project['id']}/rules")
    assert [r["name"] for r in rules.json()] == ["Margins"]
    upd_rule = await actor.patch(
        f"/api/v1/projects/{project['id']}/rules/{rule.json()['id']}", json={"is_active": False}
    )
    assert upd_rule.status_code == 200 and upd_rule.json()["is_active"] is False


async def test_workspace_update_requires_workspace_admin(client, make_user) -> None:  # type: ignore[no-untyped-def]
    owner = await make_user("owner@example.com")
    colleague = await make_user("colleague@example.com")
    ws = (await owner.post("/api/v1/workspaces", json={"name": "Shared"})).json()
    # not a member yet → 404 (existence not leaked)
    assert (await colleague.get(f"/api/v1/workspaces/{ws['id']}")).status_code == 404
    add = await owner.post(
        f"/api/v1/workspaces/{ws['id']}/members", json={"email": "colleague@example.com", "role": "member"}
    )
    assert add.status_code == 201, add.text
    assert (await colleague.get(f"/api/v1/workspaces/{ws['id']}")).json()["my_role"] == "member"
    forbidden = await colleague.patch(f"/api/v1/workspaces/{ws['id']}", json={"name": "Hijacked"})
    assert forbidden.status_code == 403 and forbidden.json()["error"]["code"] == "insufficient_role"
    ok = await owner.patch(f"/api/v1/workspaces/{ws['id']}", json={"name": "Renamed"})
    assert ok.status_code == 200 and ok.json()["name"] == "Renamed"
    members = await colleague.get(f"/api/v1/workspaces/{ws['id']}/members")
    assert {m["email"] for m in members.json()} == {"owner@example.com", "colleague@example.com"}


async def test_viewer_cannot_create(client, make_user) -> None:  # type: ignore[no-untyped-def]
    viewer = await make_user("viewer@example.com", role=Role.VIEWER)
    res = await viewer.post("/api/v1/workspaces", json={"name": "Nope"})
    assert res.status_code == 403
    admin = await make_user("admin@example.com", role=Role.ADMIN)
    ws = (await admin.post("/api/v1/workspaces", json={"name": "Visible"})).json()
    await admin.post(
        f"/api/v1/workspaces/{ws['id']}/members", json={"email": "viewer@example.com", "role": "admin"}
    )
    # org-level viewer is capped at viewer inside the workspace even if granted admin there
    assert (await viewer.get(f"/api/v1/workspaces/{ws['id']}")).json()["my_role"] == "viewer"
    assert (
        await viewer.post(f"/api/v1/workspaces/{ws['id']}/projects", json={"name": "P"})
    ).status_code == 403


async def test_org_admin_sees_all_workspaces_in_org(client, make_user) -> None:  # type: ignore[no-untyped-def]
    member = await make_user("m@example.com")
    admin = await make_user("a@example.com", role=Role.ADMIN)
    await member.post("/api/v1/workspaces", json={"name": "Private WS"})
    listing = await admin.get("/api/v1/workspaces")
    assert [w["name"] for w in listing.json()] == ["Private WS"]
    assert listing.json()[0]["my_role"] == "admin"


async def test_tenant_isolation_idor(client, make_user) -> None:  # type: ignore[no-untyped-def]
    acme = await make_user("acme@example.com", org="Acme", role=Role.ADMIN)
    globex = await make_user("globex@example.com", org="Globex", role=Role.ADMIN)
    ws = (await acme.post("/api/v1/workspaces", json={"name": "Acme WS"})).json()
    project = (await acme.post(f"/api/v1/workspaces/{ws['id']}/projects", json={"name": "Secret"})).json()
    assert (await globex.get("/api/v1/workspaces")).json() == []
    for url in (
        f"/api/v1/workspaces/{ws['id']}",
        f"/api/v1/workspaces/{ws['id']}/projects",
        f"/api/v1/projects/{project['id']}",
        f"/api/v1/projects/{project['id']}/rules",
    ):
        res = await globex.get(url)
        assert res.status_code == 404, url
    assert (
        await globex.patch(f"/api/v1/projects/{project['id']}", json={"name": "Owned"})
    ).status_code == 404
    assert (
        await globex.post(f"/api/v1/workspaces/{ws['id']}/projects", json={"name": "Inject"})
    ).status_code == 404
    # cross-org header is refused
    res = await client.get(
        "/api/v1/workspaces",
        headers={"Authorization": f"Bearer {globex.access_token}", "X-Organization-Id": acme.organization_id},
    )
    assert res.status_code == 403 and res.json()["error"]["code"] == "not_a_member"


async def test_audit_log_written_for_mutations(app, make_user) -> None:  # type: ignore[no-untyped-def]
    from app.models.governance import AuditLog
    from sqlalchemy import select

    actor = await make_user("audit@example.com")
    ws = (await actor.post("/api/v1/workspaces", json={"name": "Audited"})).json()
    await actor.patch(f"/api/v1/workspaces/{ws['id']}", json={"description": "changed"})
    async with app.state.session_factory() as session:
        rows = (await session.scalars(select(AuditLog).order_by(AuditLog.created_at))).all()
    actions = [r.action for r in rows]
    assert actions == ["workspace.created", "workspace.updated"]
    assert rows[1].before_json["description"] is None and rows[1].after_json["description"] == "changed"
    assert rows[1].request_id and str(rows[1].actor_user_id)
