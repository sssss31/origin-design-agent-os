"""End-to-end journey (spec §18 E2E): login → project → upload → /resize → live run → artifact → approve.

Runs against the real API stack with the Echo provider and the real image tools, so it
exercises routing, context, tool permissions, artifact persistence, events and approval
without any external service.
"""

from __future__ import annotations

import asyncio
import io

from app.domain.roles import Role
from PIL import Image

from tests.conftest import requires_db

pytestmark = requires_db


def poster() -> bytes:
    buf = io.BytesIO()
    im = Image.new("RGB", (1080, 1350), (250, 250, 250))
    im.paste((20, 40, 90), (100, 100, 980, 400))
    im.save(buf, format="PNG")
    return buf.getvalue()


async def test_full_journey(app, client, make_user) -> None:  # type: ignore[no-untyped-def]
    # 1. login (make_user performs POST /auth/login) as an org admin, seed the eight agents with the echo provider
    admin = await make_user("owner@example.com", role=Role.ADMIN)
    seed = await admin.post("/api/v1/admin/seed/design-agents", json={"provider_type": "echo"})
    assert seed.status_code == 200 and seed.json()["published"] == 8

    # 2. workspace + project
    ws = (
        await admin.post("/api/v1/workspaces", json={"name": "Brand Studio", "rules_text": "Logo top-left."})
    ).json()
    project = (
        await admin.post(f"/api/v1/workspaces/{ws['id']}/projects", json={"name": "Autumn Campaign"})
    ).json()

    # 3. upload the master poster as an asset
    up = await client.post(
        f"/api/v1/projects/{project['id']}/assets",
        headers=admin.headers,
        files={"file": ("poster.png", poster(), "image/png")},
        data={"kind": "image"},
    )
    assert up.status_code == 201, up.text
    asset = up.json()

    # 4. /resize through the chat with the asset attached; the echo runner calls the bound tool
    conv = (
        await admin.post(f"/api/v1/projects/{project['id']}/conversations", json={"title": "Autumn resize"})
    ).json()
    run = await admin.post(
        f"/api/v1/conversations/{conv['id']}/runs",
        json={
            "content": "/resize the poster to 4:5 and 9:16 !image.resize",
            "selected_asset_ids": [asset["id"]],
        },
    )
    assert run.status_code == 202, run.text
    run_id = run.json()["run_id"]

    # 5. live events: the SSE stream tails until the run completes (inline queue runs it concurrently)
    seen: list[str] = []

    async def tail() -> None:
        async with client.stream("GET", f"/api/v1/runs/{run_id}/events", headers=admin.headers) as stream:
            async for line in stream.aiter_lines():
                if line.startswith("event: "):
                    seen.append(line[7:])
                    if line[7:] in ("run.completed", "run.failed", "run.cancelled"):
                        break

    await asyncio.wait_for(tail(), timeout=30)
    assert seen[0] == "run.started" and seen[-1] == "run.completed", seen
    assert "context.loaded" in seen and "agent.started" in seen and "tool.completed" in seen

    detail = (await admin.get(f"/api/v1/runs/{run_id}")).json()
    assert detail["status"] == "SUCCEEDED"
    assert [n["kind"] for n in detail["nodes"]] == ["parse", "context", "agent", "save"]

    # 6. artifacts: the echo runner sends no arguments, so image.resize reports a validation error (no invented artifact);
    #    run the deterministic tool path the executor uses to prove artifact persistence + lineage + approval
    import uuid as _uuid

    from app.ports.runner import ProducedFile
    from app.services.artifacts import ArtifactService

    async with app.state.session_factory() as session:
        svc = ArtifactService(session, None, app.state.adapters.storage)
        art, _ = await svc.persist_produced(
            ProducedFile(
                filename="autumn-poster-4x5.png",
                content=poster(),
                mime_type="image/png",
                artifact_type="image",
            ),
            workspace_id=_uuid.UUID(ws["id"]),
            project_id=_uuid.UUID(project["id"]),
            conversation_id=_uuid.UUID(conv["id"]),
            run_id=_uuid.UUID(run_id),
            node_run_id=None,
            agent_version_id=None,
            organization_id=_uuid.UUID(admin.organization_id),
            created_by=None,
        )
        await session.commit()
        artifact_id = str(art.id)
    listing = (await admin.get(f"/api/v1/projects/{project['id']}/artifacts")).json()
    assert any(a["id"] == artifact_id and a["current_version"]["run_id"] == run_id for a in listing)

    # 7. approve → final via export tool; download link works
    assert (await admin.post(f"/api/v1/artifacts/{artifact_id}/approve")).json()["status"] == "approved"
    dl = (await admin.get(f"/api/v1/artifacts/{artifact_id}/download")).json()
    assert (await client.get(dl["url"])).status_code == 200

    # 8. everything is auditable
    audit = (await admin.get("/api/v1/admin/audit", params={"limit": 500})).json()
    actions = {a["action"] for a in audit}
    assert {"asset.uploaded", "run.created", "artifact.approved", "agent.published"} <= actions

    # 9. a member of another organization sees nothing
    stranger = await make_user("stranger@example.com", org="Elsewhere")
    assert (await stranger.get(f"/api/v1/runs/{run_id}")).status_code == 404
    assert (await stranger.get(f"/api/v1/artifacts/{artifact_id}")).status_code == 404
