"""Tool definitions (spec §12). Schema/config changes create a new published tool version."""

from __future__ import annotations

import uuid

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.authz import AuthContext
from app.core.errors import Conflict, NotFound
from app.db.base import utcnow
from app.models.tools import Tool, ToolPermission, ToolVersion
from app.ports.secrets import SecretStore
from app.schemas.admin import ToolCreate, ToolPermissionIn, ToolUpdate
from app.services import audit

VERSIONED_FIELDS = {"input_schema", "output_schema", "config", "timeout_seconds"}


class ToolService:
    def __init__(self, session: AsyncSession, ctx: AuthContext) -> None:
        self.session = session
        self.ctx = ctx
        self.org_id = ctx.require_organization()

    async def _audit(
        self, action: str, entity_id: uuid.UUID, before: dict | None = None, after: dict | None = None
    ) -> None:
        await audit.record(
            self.session,
            action=action,
            entity_type="tool",
            entity_id=entity_id,
            organization_id=self.org_id,
            actor_user_id=self.ctx.user_id,
            before=before,
            after=after,
            request_id=self.ctx.request_id,
            ip_address=self.ctx.ip_address,
        )

    def _query(self) -> Select[tuple[Tool]]:
        return (
            select(Tool)
            .options(selectinload(Tool.versions), selectinload(Tool.permissions))
            .where(Tool.organization_id == self.org_id)
        )

    async def list(self) -> list[Tool]:
        return list((await self.session.scalars(self._query().order_by(Tool.slug))).all())

    async def get(self, tool_id: uuid.UUID) -> Tool:
        row = await self.session.scalar(
            self._query().where(Tool.id == tool_id).execution_options(populate_existing=True)
        )
        if row is None:
            raise NotFound("Tool not found", code="tool_not_found")
        return row

    @staticmethod
    def active_version(tool: Tool) -> ToolVersion | None:
        return next((v for v in tool.versions if v.id == tool.active_version_id), None)

    async def create(self, data: ToolCreate, *, is_builtin: bool = False) -> Tool:
        if await self.session.scalar(
            select(Tool.id).where(Tool.organization_id == self.org_id, Tool.slug == data.slug)
        ):
            raise Conflict(f"Tool slug '{data.slug}' already exists", code="slug_taken")
        tool = Tool(
            organization_id=self.org_id,
            slug=data.slug,
            display_name=data.display_name,
            description=data.description,
            executor_type=data.executor_type,
            status=data.status,
            is_builtin=is_builtin,
            created_by=self.ctx.user_id,
            updated_by=self.ctx.user_id,
        )
        self.session.add(tool)
        await self.session.flush()
        version = ToolVersion(
            tool_id=tool.id,
            version=1,
            input_schema=data.input_schema,
            output_schema=data.output_schema,
            config=data.config,
            timeout_seconds=data.timeout_seconds,
            published_at=utcnow(),
            created_by=self.ctx.user_id,
        )
        self.session.add(version)
        await self.session.flush()
        tool.active_version_id = version.id
        await self.session.flush()
        await self._audit(
            "tool.created",
            tool.id,
            after={"slug": tool.slug, "executor_type": tool.executor_type, "version": 1},
        )
        return await self.get(tool.id)

    async def update(self, tool_id: uuid.UUID, data: ToolUpdate) -> Tool:
        tool = await self.get(tool_id)
        changes = data.model_dump(exclude_unset=True)
        before = {
            "display_name": tool.display_name,
            "description": tool.description,
            "status": tool.status,
            "active_version_id": str(tool.active_version_id),
        }
        for k in ("display_name", "description", "status"):
            if k in changes and changes[k] is not None:
                setattr(tool, k, changes[k])
        if VERSIONED_FIELDS & changes.keys():
            current = self.active_version(tool)
            new_number = max((v.version for v in tool.versions), default=0) + 1
            version = ToolVersion(
                tool_id=tool.id,
                version=new_number,
                input_schema=changes.get("input_schema", current.input_schema if current else {}),
                output_schema=changes.get("output_schema", current.output_schema if current else None),
                config=changes.get("config", current.config if current else {}),
                timeout_seconds=changes.get("timeout_seconds", current.timeout_seconds if current else 60),
                secret_ref_id=current.secret_ref_id if current else None,
                published_at=utcnow(),
                change_note=changes.get("change_note"),
                created_by=self.ctx.user_id,
            )
            self.session.add(version)
            await self.session.flush()
            tool.active_version_id = version.id
        tool.updated_by = self.ctx.user_id
        await self.session.flush()
        self.session.expire(tool, ["versions"])
        tool = await self.get(tool.id)
        await self._audit(
            "tool.updated",
            tool.id,
            before=before,
            after={
                "display_name": tool.display_name,
                "description": tool.description,
                "status": tool.status,
                "active_version_id": str(tool.active_version_id),
            },
        )
        return tool

    async def set_secret(self, tool_id: uuid.UUID, secret: str, secrets: SecretStore) -> Tool:
        tool = await self.get(tool_id)
        current = self.active_version(tool)
        if current is None:
            raise NotFound("Tool has no active version", code="tool_version_missing")
        if current.secret_ref_id:
            handle = await secrets.rotate(str(current.secret_ref_id), secret)
        else:
            handle = await secrets.store(f"tool:{tool.slug}", secret)
            current.secret_ref_id = uuid.UUID(handle.ref)
        await self.session.flush()
        await self._audit(
            "tool.secret_set", tool.id, after={"fingerprint": handle.fingerprint, "version": handle.version}
        )
        return await self.get(tool.id)

    async def set_permission(self, tool_id: uuid.UUID, data: ToolPermissionIn) -> Tool:
        tool = await self.get(tool_id)
        existing = next(
            (
                p
                for p in tool.permissions
                if p.subject_type == data.subject_type and p.subject_key == data.subject_key
            ),
            None,
        )
        before = {"allowed": existing.allowed, "limits_json": existing.limits_json} if existing else None
        if existing is None:
            self.session.add(ToolPermission(tool_id=tool.id, **data.model_dump()))
        else:
            existing.allowed, existing.limits_json = data.allowed, data.limits_json
        await self.session.flush()
        self.session.expire(tool, ["permissions"])
        await self._audit("tool.permission_set", tool.id, before=before, after=data.model_dump())
        return await self.get(tool.id)

    async def delete_permission(self, tool_id: uuid.UUID, permission_id: uuid.UUID) -> Tool:
        tool = await self.get(tool_id)
        perm = next((p for p in tool.permissions if p.id == permission_id), None)
        if perm is None:
            raise NotFound("Permission not found", code="permission_not_found")
        before = {"subject_type": perm.subject_type, "subject_key": perm.subject_key, "allowed": perm.allowed}
        await self.session.delete(perm)
        await self.session.flush()
        self.session.expire(tool, ["permissions"])
        await self._audit("tool.permission_removed", tool.id, before=before)
        return await self.get(tool.id)
