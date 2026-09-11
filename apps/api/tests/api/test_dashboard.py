from app.domain.roles import Role

from tests.conftest import requires_db

pytestmark = requires_db


async def test_quickstart_recents_library_graph_profile(app, make_user) -> None:  # type: ignore[no-untyped-def]
    admin = await make_user("admin@example.com", role=Role.ADMIN)
    assert (
        await admin.post("/api/v1/admin/seed/design-agents", json={"provider_type": "echo"})
    ).status_code == 200
    # quick start without a project creates Playground / Scratchpad and runs the command
    res = await admin.post("/api/v1/quickstart", json={"content": "/copy a tagline for autumn"})
    assert res.status_code == 202, res.text
    body = res.json()
    await app.state.adapters.queue.drain()
    recents = (await admin.get("/api/v1/conversations/recent")).json()
    assert (
        recents[0]["id"] == body["conversation_id"]
        and recents[0]["project_name"] == "Scratchpad"
        and recents[0]["workspace_name"] == "Playground"
    )
    assert recents[0]["last_message_preview"]
    # second quick start reuses the scratch project
    res2 = await admin.post("/api/v1/quickstart", json={"content": "/qc anything"})
    assert res2.json()["project_id"] == body["project_id"]
    hits = (await admin.get("/api/v1/conversations/recent", params={"search": "tagline"})).json()
    assert len(hits) == 1
    lib = (await admin.get("/api/v1/library")).json()
    assert lib["projects"][0]["name"] == "Scratchpad" and lib["assets"] == []
    graph = (await admin.get("/api/v1/agents/graph")).json()
    assert len(graph["nodes"]) == 8 and any(e["is_failure_route"] for e in graph["edges"])
    manager = next(n for n in graph["nodes"] if n["is_manager"])
    assert len([e for e in graph["edges"] if e["source"] == manager["id"]]) == 7
    profile = (await admin.get("/api/v1/me/profile")).json()
    assert profile["role"] == "admin" and profile["counts"]["conversations"] == 2
    # members of another organization see nothing
    stranger = await make_user("s@example.com", org="Other")
    assert (await stranger.get("/api/v1/conversations/recent")).json() == []
    assert (
        await stranger.post(
            "/api/v1/quickstart", json={"content": "/copy x", "project_id": body["project_id"]}
        )
    ).status_code == 404
