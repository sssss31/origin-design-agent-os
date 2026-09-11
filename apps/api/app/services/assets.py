"""Asset uploads and versions (spec §8, §16 P3)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.authz import AuthContext
from app.core.errors import NotFound
from app.domain.roles import Role
from app.models.files import Asset, AssetVersion
from app.ports.storage import ObjectStorage
from app.schemas.files import AssetUpdate
from app.services import audit
from app.services.access import ProjectAccess, resolve_project
from app.services.uploads import store_upload


class AssetService:
    def __init__(
        self,
        session: AsyncSession,
        ctx: AuthContext,
        storage: ObjectStorage,
        *,
        max_upload_bytes: int,
        signed_url_ttl: int,
    ) -> None:
        self.session = session
        self.ctx = ctx
        self.storage = storage
        self.max_upload_bytes = max_upload_bytes
        self.signed_url_ttl = signed_url_ttl

    async def _get(self, asset_id: uuid.UUID, required: Role = Role.VIEWER) -> tuple[Asset, ProjectAccess]:
        asset = await self.session.scalar(
            select(Asset)
            .options(selectinload(Asset.versions))
            .where(Asset.id == asset_id)
            .execution_options(populate_existing=True)
        )
        if asset is None:
            raise NotFound("Asset not found", code="asset_not_found")
        access = await resolve_project(self.session, self.ctx, asset.project_id)
        access.require(required)
        return asset, access

    async def list_for_project(self, project_id: uuid.UUID) -> list[Asset]:
        await resolve_project(self.session, self.ctx, project_id)
        return list(
            (
                await self.session.scalars(
                    select(Asset)
                    .options(selectinload(Asset.versions))
                    .where(Asset.project_id == project_id)
                    .order_by(Asset.created_at.desc())
                )
            ).all()
        )

    async def get(self, asset_id: uuid.UUID) -> Asset:
        asset, _ = await self._get(asset_id)
        return asset

    async def upload(
        self,
        project_id: uuid.UUID,
        *,
        filename: str,
        content_type: str,
        data: bytes,
        name: str | None,
        kind: str | None,
        description: str | None,
    ) -> Asset:
        access = await resolve_project(self.session, self.ctx, project_id)
        access.require(Role.MEMBER)
        org_id = access.workspace.organization_id
        info = await store_upload(
            self.storage,
            key_prefix=f"org/{org_id}/projects/{project_id}/assets",
            filename=filename,
            content_type=content_type,
            data=data,
            max_bytes=self.max_upload_bytes,
        )
        # The Asset row is created only after the object exists in storage (never "ready" without bytes).
        asset = Asset(
            project_id=project_id,
            name=name or info.filename,
            kind=kind or _guess_kind(info.mime_type),
            status="ready",
            description=description,
            created_by=self.ctx.user_id,
        )
        self.session.add(asset)
        await self.session.flush()
        version = AssetVersion(
            asset_id=asset.id,
            version=1,
            storage_key=info.stored.key,
            filename=info.filename,
            mime_type=info.mime_type,
            size_bytes=info.stored.size,
            checksum_sha256=info.checksum,
            width=info.width,
            height=info.height,
            metadata_json=info.metadata,
            created_by=self.ctx.user_id,
        )
        self.session.add(version)
        await self.session.flush()
        asset.current_version_id = version.id
        await self.session.flush()
        await audit.record(
            self.session,
            action="asset.uploaded",
            entity_type="asset",
            entity_id=asset.id,
            organization_id=org_id,
            actor_user_id=self.ctx.user_id,
            after={"name": asset.name, "kind": asset.kind, "mime": info.mime_type, "size": info.stored.size},
            request_id=self.ctx.request_id,
        )
        asset, _ = await self._get(asset.id)
        return asset

    async def add_version(
        self, asset_id: uuid.UUID, *, filename: str, content_type: str, data: bytes
    ) -> Asset:
        asset, access = await self._get(asset_id, Role.MEMBER)
        org_id = access.workspace.organization_id
        info = await store_upload(
            self.storage,
            key_prefix=f"org/{org_id}/projects/{asset.project_id}/assets",
            filename=filename,
            content_type=content_type,
            data=data,
            max_bytes=self.max_upload_bytes,
        )
        number = max((v.version for v in asset.versions), default=0) + 1
        version = AssetVersion(
            asset_id=asset.id,
            version=number,
            storage_key=info.stored.key,
            filename=info.filename,
            mime_type=info.mime_type,
            size_bytes=info.stored.size,
            checksum_sha256=info.checksum,
            width=info.width,
            height=info.height,
            metadata_json=info.metadata,
            created_by=self.ctx.user_id,
        )
        self.session.add(version)
        await self.session.flush()
        asset.current_version_id = version.id
        asset.status = "ready"
        await self.session.flush()
        await audit.record(
            self.session,
            action="asset.version_added",
            entity_type="asset",
            entity_id=asset.id,
            organization_id=org_id,
            actor_user_id=self.ctx.user_id,
            after={"version": number, "size": info.stored.size},
            request_id=self.ctx.request_id,
        )
        asset, _ = await self._get(asset.id)
        return asset

    async def update(self, asset_id: uuid.UUID, data: AssetUpdate) -> Asset:
        asset, access = await self._get(asset_id, Role.MEMBER)
        for k, v in data.model_dump(exclude_unset=True).items():
            if v is not None:
                setattr(asset, k, v)
        await self.session.flush()
        await audit.record(
            self.session,
            action="asset.updated",
            entity_type="asset",
            entity_id=asset.id,
            organization_id=access.workspace.organization_id,
            actor_user_id=self.ctx.user_id,
            after=data.model_dump(exclude_unset=True),
            request_id=self.ctx.request_id,
        )
        asset, _ = await self._get(asset.id)
        return asset

    async def download_url(
        self, asset_id: uuid.UUID, version_id: uuid.UUID | None = None
    ) -> tuple[str, AssetVersion]:
        asset, _ = await self._get(asset_id)
        version = next((v for v in asset.versions if v.id == (version_id or asset.current_version_id)), None)
        if version is None:
            raise NotFound("Asset version not found", code="asset_version_not_found")
        url = await self.storage.presign_download(
            version.storage_key, expires_in=self.signed_url_ttl, filename=version.filename
        )
        return url, version


def _guess_kind(mime: str) -> str:
    if mime == "image/svg+xml":
        return "svg"
    if mime.startswith("image/"):
        return "image"
    if mime == "application/pdf":
        return "pdf"
    if mime.startswith("font/"):
        return "font"
    return "other"
