from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz import AuthContext
from app.core.errors import Conflict, Forbidden, NotFound
from app.domain.roles import Role, has_at_least
from app.domain.slugs import slugify
from app.models.identity import OrganizationMember, User
from app.models.workspace import Workspace, WorkspaceMember
from app.schemas.workspace import WorkspaceCreate, WorkspaceMemberAdd, WorkspaceUpdate
from app.services import audit
from app.services.access import WorkspaceAccess, resolve_workspace


def _snapshot(ws: Workspace) -> dict:
    return {
        "name": ws.name,
        "slug": ws.slug,
        "description": ws.description,
        "status": ws.status,
        "brand_config": ws.brand_config,
        "rules_text": ws.rules_text,
    }


class WorkspaceService:
    def __init__(self, session: AsyncSession, ctx: AuthContext) -> None:
        self.session = session
        self.ctx = ctx

    async def list_visible(self) -> list[tuple[Workspace, Role]]:
        org_ids = [self.ctx.organization_id] if self.ctx.organization_id else list(self.ctx.memberships)
        if not org_ids:
            return []
        rows = (
            await self.session.execute(
                select(Workspace, WorkspaceMember.role)
                .outerjoin(
                    WorkspaceMember,
                    (WorkspaceMember.workspace_id == Workspace.id)
                    & (WorkspaceMember.user_id == self.ctx.user_id),
                )
                .where(Workspace.organization_id.in_(org_ids))
                .order_by(Workspace.created_at.desc())
            )
        ).all()
        out: list[tuple[Workspace, Role]] = []
        for ws, member_role in rows:
            org_role = self.ctx.role_in(ws.organization_id)
            if org_role == Role.ADMIN:
                out.append((ws, Role.ADMIN))
            elif member_role is not None:
                out.append((ws, Role.VIEWER if org_role == Role.VIEWER else Role(member_role)))
        return out

    async def create(self, data: WorkspaceCreate) -> tuple[Workspace, Role]:
        org_id = self.ctx.require_organization(data.organization_id)
        if not has_at_least(self.ctx.role_in(org_id), Role.MEMBER):
            raise Forbidden("Viewers cannot create workspaces", code="insufficient_role")
        slug = data.slug or slugify(data.name)
        exists = await self.session.scalar(
            select(Workspace.id).where(Workspace.organization_id == org_id, Workspace.slug == slug)
        )
        if exists:
            raise Conflict(f"Workspace slug '{slug}' already exists in this organization", code="slug_taken")
        ws = Workspace(
            organization_id=org_id,
            name=data.name,
            slug=slug,
            description=data.description,
            brand_config=data.brand_config,
            rules_text=data.rules_text,
            created_by=self.ctx.user_id,
            updated_by=self.ctx.user_id,
        )
        self.session.add(ws)
        await self.session.flush()
        self.session.add(WorkspaceMember(workspace_id=ws.id, user_id=self.ctx.user_id, role=Role.ADMIN))
        await self.session.flush()
        await self.session.refresh(ws)
        await audit.record(
            self.session,
            action="workspace.created",
            entity_type="workspace",
            entity_id=ws.id,
            organization_id=org_id,
            actor_user_id=self.ctx.user_id,
            after=_snapshot(ws),
            request_id=self.ctx.request_id,
            ip_address=self.ctx.ip_address,
        )
        return ws, Role.ADMIN

    async def get(self, workspace_id: uuid.UUID) -> WorkspaceAccess:
        return await resolve_workspace(self.session, self.ctx, workspace_id)

    async def update(self, workspace_id: uuid.UUID, data: WorkspaceUpdate) -> WorkspaceAccess:
        access = await self.get(workspace_id)
        access.require(Role.ADMIN)
        ws = access.workspace
        before = _snapshot(ws)
        for field_name, value in data.model_dump(exclude_unset=True).items():
            setattr(ws, field_name, value)
        ws.updated_by = self.ctx.user_id
        await self.session.flush()
        await self.session.refresh(ws)
        await audit.record(
            self.session,
            action="workspace.updated",
            entity_type="workspace",
            entity_id=ws.id,
            organization_id=ws.organization_id,
            actor_user_id=self.ctx.user_id,
            before=before,
            after=_snapshot(ws),
            request_id=self.ctx.request_id,
            ip_address=self.ctx.ip_address,
        )
        return access

    async def list_members(self, workspace_id: uuid.UUID) -> list[tuple[User, Role]]:
        await self.get(workspace_id)
        rows = (
            await self.session.execute(
                select(User, WorkspaceMember.role)
                .join(WorkspaceMember, WorkspaceMember.user_id == User.id)
                .where(WorkspaceMember.workspace_id == workspace_id)
                .order_by(User.email)
            )
        ).all()
        return [(u, Role(r)) for u, r in rows]

    async def add_member(self, workspace_id: uuid.UUID, data: WorkspaceMemberAdd) -> tuple[User, Role]:
        access = await self.get(workspace_id)
        access.require(Role.ADMIN)
        ws = access.workspace
        user = await self.session.scalar(select(User).where(User.email == data.email.lower()))
        if user is None:
            raise NotFound("User not found", code="user_not_found")
        in_org = await self.session.scalar(
            select(OrganizationMember.id).where(
                OrganizationMember.organization_id == ws.organization_id,
                OrganizationMember.user_id == user.id,
            )
        )
        if not in_org:
            raise Conflict("User is not a member of this organization", code="not_in_organization")
        member = await self.session.scalar(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == ws.id, WorkspaceMember.user_id == user.id
            )
        )
        before = {"role": member.role} if member else None
        if member is None:
            member = WorkspaceMember(workspace_id=ws.id, user_id=user.id, role=data.role)
            self.session.add(member)
        else:
            member.role = data.role
        await self.session.flush()
        await audit.record(
            self.session,
            action="workspace.member_set",
            entity_type="workspace_member",
            entity_id=member.id,
            organization_id=ws.organization_id,
            actor_user_id=self.ctx.user_id,
            before=before,
            after={"user_id": str(user.id), "role": data.role},
            request_id=self.ctx.request_id,
            ip_address=self.ctx.ip_address,
        )
        return user, Role(data.role)
