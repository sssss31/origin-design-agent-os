from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.registry import Adapters
from app.core.authz import DB, Auth, AuthContext, Config
from app.core.config import Settings
from app.core.deps import AdaptersDep
from app.models.files import Asset
from app.schemas.common import from_orm
from app.schemas.files import AssetOut, AssetUpdate, AssetVersionOut, DownloadOut
from app.services.assets import AssetService

router = APIRouter(tags=["assets"])


def _svc(session: AsyncSession, ctx: AuthContext, adapters: Adapters, settings: Settings) -> AssetService:
    return AssetService(
        session,
        ctx,
        adapters.storage,
        max_upload_bytes=settings.max_upload_mb * 1024 * 1024,
        signed_url_ttl=settings.signed_url_ttl_seconds,
    )


def _out(a: Asset) -> AssetOut:
    current = next((v for v in a.versions if v.id == a.current_version_id), None)
    return from_orm(
        AssetOut,
        a,
        current_version=from_orm(AssetVersionOut, current) if current else None,
        versions=[from_orm(AssetVersionOut, v) for v in a.versions],
    )


@router.get("/projects/{project_id}/assets", response_model=list[AssetOut])
async def list_assets(
    project_id: uuid.UUID, ctx: Auth, session: DB, adapters: AdaptersDep, settings: Config
) -> list[AssetOut]:
    return [_out(a) for a in await _svc(session, ctx, adapters, settings).list_for_project(project_id)]


@router.post("/projects/{project_id}/assets", response_model=AssetOut, status_code=status.HTTP_201_CREATED)
async def upload_asset(
    project_id: uuid.UUID,
    ctx: Auth,
    session: DB,
    adapters: AdaptersDep,
    settings: Config,
    file: Annotated[UploadFile, File()],
    name: Annotated[str | None, Form()] = None,
    kind: Annotated[str | None, Form()] = None,
    description: Annotated[str | None, Form()] = None,
) -> AssetOut:
    data = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    asset = await _svc(session, ctx, adapters, settings).upload(
        project_id,
        filename=file.filename or "file",
        content_type=file.content_type or "",
        data=data,
        name=name,
        kind=kind,
        description=description,
    )
    return _out(asset)


@router.get("/assets/{asset_id}", response_model=AssetOut)
async def get_asset(
    asset_id: uuid.UUID, ctx: Auth, session: DB, adapters: AdaptersDep, settings: Config
) -> AssetOut:
    return _out(await _svc(session, ctx, adapters, settings).get(asset_id))


@router.patch("/assets/{asset_id}", response_model=AssetOut)
async def update_asset(
    asset_id: uuid.UUID, body: AssetUpdate, ctx: Auth, session: DB, adapters: AdaptersDep, settings: Config
) -> AssetOut:
    return _out(await _svc(session, ctx, adapters, settings).update(asset_id, body))


@router.post("/assets/{asset_id}/versions", response_model=AssetOut, status_code=status.HTTP_201_CREATED)
async def add_asset_version(
    asset_id: uuid.UUID,
    ctx: Auth,
    session: DB,
    adapters: AdaptersDep,
    settings: Config,
    file: Annotated[UploadFile, File()],
) -> AssetOut:
    data = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    return _out(
        await _svc(session, ctx, adapters, settings).add_version(
            asset_id, filename=file.filename or "file", content_type=file.content_type or "", data=data
        )
    )


@router.get("/assets/{asset_id}/download", response_model=DownloadOut)
async def download_asset(
    asset_id: uuid.UUID,
    ctx: Auth,
    session: DB,
    adapters: AdaptersDep,
    settings: Config,
    version_id: uuid.UUID | None = None,
) -> DownloadOut:
    url, version = await _svc(session, ctx, adapters, settings).download_url(asset_id, version_id)
    return DownloadOut(
        url=url,
        expires_in=settings.signed_url_ttl_seconds,
        filename=version.filename,
        mime_type=version.mime_type,
    )
