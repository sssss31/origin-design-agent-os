"""Phase 3 acceptance: persistent chat, authorized uploads/downloads, versioned artifacts."""

from __future__ import annotations

import io

from app.domain.roles import Role
from PIL import Image

from tests.conftest import requires_db

pytestmark = requires_db


def png_bytes(w: int = 64, h: int = 32) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (10, 20, 30)).save(buf, format="PNG")
    return buf.getvalue()


async def _project(actor):  # type: ignore[no-untyped-def]
    ws = (await actor.post("/api/v1/workspaces", json={"name": "WS"})).json()
    return (await actor.post(f"/api/v1/workspaces/{ws['id']}/projects", json={"name": "Autumn"})).json()


async def test_chat_persists_and_is_searchable(app, make_user) -> None:  # type: ignore[no-untyped-def]
    actor = await make_user("chat@example.com")
    project = await _project(actor)
    res = await actor.post(f"/api/v1/projects/{project['id']}/conversations", json={})
    assert res.status_code == 201, res.text
    conv = res.json()
    assert conv["title"] == "New chat"
    res = await actor.post(
        f"/api/v1/conversations/{conv['id']}/messages", json={"content": "/resize make the poster 4:5 please"}
    )
    assert res.status_code == 201, res.text
    msg = res.json()
    assert msg["command"] == "/resize" and msg["role"] == "user" and msg["content"].startswith("/resize")
    conv2 = (await actor.get(f"/api/v1/conversations/{conv['id']}")).json()
    assert conv2["title"] == "make the poster 4:5 please" and conv2["last_message_at"]

    # a second message without command, then listing returns chronological order (survives "restart": new session each request)
    await actor.post(f"/api/v1/conversations/{conv['id']}/messages", json={"content": "and keep the logo"})
    msgs = (await actor.get(f"/api/v1/conversations/{conv['id']}/messages")).json()
    assert [m["content"][:7] for m in msgs] == ["/resize", "and kee"]

    hits = (await actor.get(f"/api/v1/projects/{project['id']}/messages/search", params={"q": "logo"})).json()
    assert len(hits) == 1 and hits[0]["conversation_title"] == conv2["title"]

    # rename + archive + list filters
    assert (await actor.patch(f"/api/v1/conversations/{conv['id']}", json={"title": "Poster resize"})).json()[
        "title"
    ] == "Poster resize"
    await actor.patch(f"/api/v1/conversations/{conv['id']}", json={"status": "archived"})
    assert (await actor.get(f"/api/v1/projects/{project['id']}/conversations")).json() == []
    assert (
        len(
            (
                await actor.get(
                    f"/api/v1/projects/{project['id']}/conversations", params={"include_archived": "true"}
                )
            ).json()
        )
        == 1
    )


async def test_asset_upload_validation_and_signed_download(app, client, make_user) -> None:  # type: ignore[no-untyped-def]
    actor = await make_user("files@example.com")
    project = await _project(actor)
    res = await client.post(
        f"/api/v1/projects/{project['id']}/assets",
        headers=actor.headers,
        files={"file": ("logo.png", png_bytes(), "image/png")},
        data={"kind": "logo", "description": "Primary logo"},
    )
    assert res.status_code == 201, res.text
    asset = res.json()
    assert asset["status"] == "ready" and asset["kind"] == "logo"
    assert (
        asset["current_version"]["width"] == 64
        and asset["current_version"]["height"] == 32
        and asset["current_version"]["mime_type"] == "image/png"
    )

    # rejected uploads: bad type, extension mismatch, empty, path traversal in filename is sanitised
    bad = await client.post(
        f"/api/v1/projects/{project['id']}/assets",
        headers=actor.headers,
        files={"file": ("x.exe", b"MZ", "application/x-msdownload")},
    )
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "unsupported_file_type"
    bad = await client.post(
        f"/api/v1/projects/{project['id']}/assets",
        headers=actor.headers,
        files={"file": ("photo.png", png_bytes(), "image/jpeg")},
    )
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "extension_mismatch"
    bad = await client.post(
        f"/api/v1/projects/{project['id']}/assets",
        headers=actor.headers,
        files={"file": ("empty.png", b"", "image/png")},
    )
    assert bad.status_code == 422
    weird = await client.post(
        f"/api/v1/projects/{project['id']}/assets",
        headers=actor.headers,
        files={"file": ("../../etc/passwd.png", png_bytes(), "image/png")},
    )
    assert weird.status_code == 201 and weird.json()["current_version"]["filename"] == "passwd.png"

    # new version
    res = await client.post(
        f"/api/v1/assets/{asset['id']}/versions",
        headers=actor.headers,
        files={"file": ("logo-v2.png", png_bytes(128, 64), "image/png")},
    )
    assert (
        res.status_code == 201
        and res.json()["current_version"]["version"] == 2
        and len(res.json()["versions"]) == 2
    )

    # signed download works, tampered signature fails, other tenant gets 404
    dl = await actor.get(f"/api/v1/assets/{asset['id']}/download")
    assert dl.status_code == 200, dl.text
    url = dl.json()["url"]
    assert url.startswith("/api/v1/files/") and "signature=" in url
    got = await client.get(url)
    assert (
        got.status_code == 200
        and got.content == png_bytes(128, 64)
        and got.headers["content-type"].startswith("image/png")
    )
    assert got.headers["content-security-policy"] == "sandbox"
    sig = url.split("signature=")[1].split("&")[0]
    tampered = await client.get(url.replace(f"signature={sig}", f"signature={sig[:-4]}zzzz"))
    assert tampered.status_code == 403
    stranger = await make_user("stranger@example.com", org="Other")
    assert (await stranger.get(f"/api/v1/assets/{asset['id']}/download")).status_code == 404
    assert (await stranger.get(f"/api/v1/projects/{project['id']}/assets")).status_code == 404

    # attach the asset to a message
    conv = (
        await actor.post(f"/api/v1/projects/{project['id']}/conversations", json={"title": "with files"})
    ).json()
    msg = await actor.post(
        f"/api/v1/conversations/{conv['id']}/messages",
        json={"content": "use this logo", "asset_ids": [asset["id"]]},
    )
    assert msg.status_code == 201 and msg.json()["attachments"][0]["asset_id"] == asset["id"]
    foreign = await actor.post(
        f"/api/v1/conversations/{conv['id']}/messages",
        json={"content": "x", "asset_ids": [weird.json()["id"]]},
    )
    assert foreign.status_code == 201  # same project
    viewer = await make_user("viewer@example.com", role=Role.VIEWER)
    assert (
        await viewer.get(f"/api/v1/projects/{project['id']}/assets")
    ).status_code == 404  # not a workspace member


async def test_artifact_lifecycle_and_lineage(app, make_user) -> None:  # type: ignore[no-untyped-def]
    from app.ports.runner import ProducedFile
    from app.services.artifacts import ArtifactService

    actor = await make_user("art@example.com")
    project = await _project(actor)
    async with app.state.session_factory() as session:
        from app.models.workspace import Project

        p = await session.get(Project, project["id"])
        from app.models.workspace import Workspace

        ws = await session.get(Workspace, p.workspace_id)
        svc = ArtifactService(session, None, app.state.adapters.storage)
        master, mv = await svc.persist_produced(
            ProducedFile(
                filename="master.png",
                content=png_bytes(1080, 1350),
                mime_type="image/png",
                artifact_type="image",
            ),
            workspace_id=ws.id,
            project_id=p.id,
            conversation_id=None,
            run_id=None,
            node_run_id=None,
            agent_version_id=None,
            organization_id=ws.organization_id,
            created_by=None,
        )
        child, _ = await svc.persist_produced(
            ProducedFile(
                filename="story.png",
                content=png_bytes(1080, 1920),
                mime_type="image/png",
                artifact_type="image",
            ),
            workspace_id=ws.id,
            project_id=p.id,
            conversation_id=None,
            run_id=None,
            node_run_id=None,
            agent_version_id=None,
            organization_id=ws.organization_id,
            created_by=None,
            parent_artifact_id=master.id,
        )
        await session.commit()
        master_id, child_id = str(master.id), str(child.id)
    listing = await actor.get(f"/api/v1/projects/{project['id']}/artifacts")
    assert {a["name"] for a in listing.json()} == {"master.png", "story.png"}
    art = (await actor.get(f"/api/v1/artifacts/{master_id}")).json()
    assert (
        art["status"] == "generated"
        and art["current_version"]["width"] == 1080
        and art["current_version"]["version_number"] == 1
    )
    # approve → final; illegal transitions refused; qc_failed keeps it non-final
    assert (await actor.post(f"/api/v1/artifacts/{master_id}/approve")).json()["status"] == "approved"
    assert (await actor.post(f"/api/v1/artifacts/{master_id}/status", json={"status": "final"})).json()[
        "status"
    ] == "final"
    bad = await actor.post(f"/api/v1/artifacts/{master_id}/status", json={"status": "generated"})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "illegal_artifact_transition"
    assert (await actor.post(f"/api/v1/artifacts/{child_id}/status", json={"status": "qc_failed"})).json()[
        "status"
    ] == "qc_failed"
    assert (await actor.post(f"/api/v1/artifacts/{child_id}/approve")).status_code == 422
    lineage = (await actor.get(f"/api/v1/artifacts/{child_id}/lineage")).json()
    assert lineage["artifact"]["id"] == master_id and lineage["children"][0]["artifact"]["id"] == child_id
    dl = await actor.get(f"/api/v1/artifacts/{child_id}/download")
    assert dl.status_code == 200 and dl.json()["filename"] == "story.png"
    stranger = await make_user("s2@example.com", org="Other")
    assert (await stranger.get(f"/api/v1/artifacts/{child_id}")).status_code == 404
