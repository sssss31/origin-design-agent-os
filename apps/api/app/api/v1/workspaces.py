from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.core.authz import DB, Auth
from app.domain.roles import Role
from app.models.workspace import Workspace
from app.schemas.common import from_orm
from app.schemas.workspace import (
    ProjectCreate,
    ProjectOut,
    WorkspaceCreate,
    WorkspaceMemberAdd,
    WorkspaceMemberOut,
    WorkspaceOut,
    WorkspaceUpdate,
)
from app.services.projects import ProjectService
from app.services.workspaces import WorkspaceService

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


def _out(ws: Workspace, role: Role) -> WorkspaceOut:
    return from_orm(WorkspaceOut, ws, my_role=role)


@router.get("", response_model=list[WorkspaceOut])
async def list_workspaces(ctx: Auth, session: DB) -> list[WorkspaceOut]:
    return [_out(ws, role) for ws, role in await WorkspaceService(session, ctx).list_visible()]


@router.post("", response_model=WorkspaceOut, status_code=status.HTTP_201_CREATED)
async def create_workspace(body: WorkspaceCreate, ctx: Auth, session: DB) -> WorkspaceOut:
    ws, role = await WorkspaceService(session, ctx).create(body)
    return _out(ws, role)


@router.get("/{workspace_id}", response_model=WorkspaceOut)
async def get_workspace(workspace_id: uuid.UUID, ctx: Auth, session: DB) -> WorkspaceOut:
    access = await WorkspaceService(session, ctx).get(workspace_id)
    return _out(access.workspace, access.role)


@router.patch("/{workspace_id}", response_model=WorkspaceOut)
async def update_workspace(
    workspace_id: uuid.UUID, body: WorkspaceUpdate, ctx: Auth, session: DB
) -> WorkspaceOut:
    access = await WorkspaceService(session, ctx).update(workspace_id, body)
    return _out(access.workspace, access.role)


@router.get("/{workspace_id}/members", response_model=list[WorkspaceMemberOut])
async def list_members(workspace_id: uuid.UUID, ctx: Auth, session: DB) -> list[WorkspaceMemberOut]:
    rows = await WorkspaceService(session, ctx).list_members(workspace_id)
    return [
        WorkspaceMemberOut(user_id=u.id, email=u.email, display_name=u.display_name, role=r) for u, r in rows
    ]


@router.post(
    "/{workspace_id}/members", response_model=WorkspaceMemberOut, status_code=status.HTTP_201_CREATED
)
async def add_member(
    workspace_id: uuid.UUID, body: WorkspaceMemberAdd, ctx: Auth, session: DB
) -> WorkspaceMemberOut:
    user, role = await WorkspaceService(session, ctx).add_member(workspace_id, body)
    return WorkspaceMemberOut(user_id=user.id, email=user.email, display_name=user.display_name, role=role)


@router.get("/{workspace_id}/projects", response_model=list[ProjectOut])
async def list_projects(workspace_id: uuid.UUID, ctx: Auth, session: DB) -> list[ProjectOut]:
    rows = await ProjectService(session, ctx).list_in_workspace(workspace_id)
    return [from_orm(ProjectOut, p, my_role=role) for p, role in rows]


@router.post("/{workspace_id}/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(workspace_id: uuid.UUID, body: ProjectCreate, ctx: Auth, session: DB) -> ProjectOut:
    project, role = await ProjectService(session, ctx).create(workspace_id, body)
    return from_orm(ProjectOut, project, my_role=role)
