"""Workspace / project access resolution. Returns 404 (not 403) for objects outside the
caller's tenant so that existence is never leaked (spec §18 IDOR)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz import AuthContext
from app.core.errors import Forbidden, NotFound
from app.domain.roles import Role, has_at_least
from app.models.workspace import Project, Workspace, WorkspaceMember


@dataclass(slots=True)
class WorkspaceAccess:
    workspace: Workspace
    role: Role

    def require(self, required: Role) -> None:
        if not has_at_least(self.role, required):
            raise Forbidden(f"Requires {required} role in this workspace", code="insufficient_role")


@dataclass(slots=True)
class ProjectAccess:
    project: Project
    workspace: Workspace
    role: Role

    def require(self, required: Role) -> None:
        if not has_at_least(self.role, required):
            raise Forbidden(f"Requires {required} role in this workspace", code="insufficient_role")


async def effective_workspace_role(
    session: AsyncSession, ctx: AuthContext, workspace: Workspace
) -> Role | None:
    org_role = ctx.role_in(workspace.organization_id)
    if org_role is None:
        return None
    if org_role == Role.ADMIN:
        return Role.ADMIN
    member = await session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace.id, WorkspaceMember.user_id == ctx.user_id
        )
    )
    if member is None:
        return None
    role = Role(member.role)
    # An org viewer can never exceed viewer inside a workspace.
    return Role.VIEWER if org_role == Role.VIEWER else role


async def resolve_workspace(
    session: AsyncSession, ctx: AuthContext, workspace_id: uuid.UUID
) -> WorkspaceAccess:
    workspace = await session.get(Workspace, workspace_id)
    if workspace is None:
        raise NotFound("Workspace not found", code="workspace_not_found")
    role = await effective_workspace_role(session, ctx, workspace)
    if role is None:
        raise NotFound("Workspace not found", code="workspace_not_found")
    return WorkspaceAccess(workspace=workspace, role=role)


async def resolve_project(session: AsyncSession, ctx: AuthContext, project_id: uuid.UUID) -> ProjectAccess:
    project = await session.get(Project, project_id)
    if project is None:
        raise NotFound("Project not found", code="project_not_found")
    access = await resolve_workspace(session, ctx, project.workspace_id)
    return ProjectAccess(project=project, workspace=access.workspace, role=access.role)
