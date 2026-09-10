from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.core.authz import DB, Auth
from app.schemas.common import from_orm
from app.schemas.workspace import (
    ProjectOut,
    ProjectRuleCreate,
    ProjectRuleOut,
    ProjectRuleUpdate,
    ProjectUpdate,
)
from app.services.projects import ProjectService

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(project_id: uuid.UUID, ctx: Auth, session: DB) -> ProjectOut:
    access = await ProjectService(session, ctx).get(project_id)
    return from_orm(ProjectOut, access.project, my_role=access.role)


@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(project_id: uuid.UUID, body: ProjectUpdate, ctx: Auth, session: DB) -> ProjectOut:
    access = await ProjectService(session, ctx).update(project_id, body)
    return from_orm(ProjectOut, access.project, my_role=access.role)


@router.get("/{project_id}/rules", response_model=list[ProjectRuleOut])
async def list_rules(project_id: uuid.UUID, ctx: Auth, session: DB) -> list[ProjectRuleOut]:
    return [
        ProjectRuleOut.model_validate(r) for r in await ProjectService(session, ctx).list_rules(project_id)
    ]


@router.post("/{project_id}/rules", response_model=ProjectRuleOut, status_code=status.HTTP_201_CREATED)
async def create_rule(
    project_id: uuid.UUID, body: ProjectRuleCreate, ctx: Auth, session: DB
) -> ProjectRuleOut:
    return ProjectRuleOut.model_validate(await ProjectService(session, ctx).create_rule(project_id, body))


@router.patch("/{project_id}/rules/{rule_id}", response_model=ProjectRuleOut)
async def update_rule(
    project_id: uuid.UUID, rule_id: uuid.UUID, body: ProjectRuleUpdate, ctx: Auth, session: DB
) -> ProjectRuleOut:
    return ProjectRuleOut.model_validate(
        await ProjectService(session, ctx).update_rule(project_id, rule_id, body)
    )
