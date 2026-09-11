from __future__ import annotations

import uuid

from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.registry import Adapters
from app.core.authz import DB, Auth, AuthContext, Config
from app.core.config import Settings
from app.core.deps import AdaptersDep
from app.schemas.files import ArtifactOut, ArtifactStatusUpdate, DownloadOut, LineageNode
from app.services.artifacts import ArtifactService, artifact_out, artifacts_out

router = APIRouter(tags=["artifacts"])


def _svc(session: AsyncSession, ctx: AuthContext, adapters: Adapters, settings: Settings) -> ArtifactService:
    return ArtifactService(session, ctx, adapters.storage, signed_url_ttl=settings.signed_url_ttl_seconds)


@router.get("/projects/{project_id}/artifacts", response_model=list[ArtifactOut])
async def list_artifacts(
    project_id: uuid.UUID,
    ctx: Auth,
    session: DB,
    adapters: AdaptersDep,
    settings: Config,
    status: str | None = None,
    type: str | None = None,
) -> list[ArtifactOut]:
    return await artifacts_out(
        session,
        await _svc(session, ctx, adapters, settings).list_for_project(
            project_id, status=status, artifact_type=type
        ),
    )


@router.get("/artifacts/{artifact_id}", response_model=ArtifactOut)
async def get_artifact(
    artifact_id: uuid.UUID, ctx: Auth, session: DB, adapters: AdaptersDep, settings: Config
) -> ArtifactOut:
    return (await artifacts_out(session, [await _svc(session, ctx, adapters, settings).get(artifact_id)]))[0]


@router.post("/artifacts/{artifact_id}/approve", response_model=ArtifactOut)
async def approve_artifact(
    artifact_id: uuid.UUID, ctx: Auth, session: DB, adapters: AdaptersDep, settings: Config
) -> ArtifactOut:
    return artifact_out(await _svc(session, ctx, adapters, settings).approve(artifact_id))


@router.post("/artifacts/{artifact_id}/status", response_model=ArtifactOut)
async def set_artifact_status(
    artifact_id: uuid.UUID,
    body: ArtifactStatusUpdate,
    ctx: Auth,
    session: DB,
    adapters: AdaptersDep,
    settings: Config,
) -> ArtifactOut:
    return artifact_out(await _svc(session, ctx, adapters, settings).set_status(artifact_id, body.status))


@router.get("/artifacts/{artifact_id}/download", response_model=DownloadOut)
async def download_artifact(
    artifact_id: uuid.UUID,
    ctx: Auth,
    session: DB,
    adapters: AdaptersDep,
    settings: Config,
    version_id: uuid.UUID | None = None,
) -> DownloadOut:
    url, version = await _svc(session, ctx, adapters, settings).download_url(artifact_id, version_id)
    return DownloadOut(
        url=url,
        expires_in=settings.signed_url_ttl_seconds,
        filename=version.filename,
        mime_type=version.mime_type,
    )


@router.get("/artifacts/{artifact_id}/lineage", response_model=LineageNode)
async def artifact_lineage(
    artifact_id: uuid.UUID, ctx: Auth, session: DB, adapters: AdaptersDep, settings: Config
) -> LineageNode:
    return await _svc(session, ctx, adapters, settings).lineage(artifact_id)
