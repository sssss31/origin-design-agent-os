from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz import AuthContext
from app.core.errors import Conflict, NotFound
from app.domain.roles import Role
from app.domain.slugs import slugify
from app.models.workspace import Project, ProjectRule
from app.schemas.workspace import ProjectCreate, ProjectRuleCreate, ProjectRuleUpdate, ProjectUpdate
from app.services import audit
from app.services.access import ProjectAccess, resolve_project, resolve_workspace


def _snapshot(p: Project) -> dict:
    return {
        "name": p.name,
        "slug": p.slug,
        "description": p.description,
        "status": p.status,
        "settings_json": p.settings_json,
        "summary_text": p.summary_text,
    }


class ProjectService:
    def __init__(self, session: AsyncSession, ctx: AuthContext) -> None:
        self.session = session
        self.ctx = ctx

    async def list_in_workspace(self, workspace_id: uuid.UUID) -> list[tuple[Project, Role]]:
        access = await resolve_workspace(self.session, self.ctx, workspace_id)
        rows = (
            await self.session.scalars(
                select(Project)
                .where(Project.workspace_id == workspace_id)
                .order_by(Project.created_at.desc())
            )
        ).all()
        return [(p, access.role) for p in rows]

    async def create(self, workspace_id: uuid.UUID, data: ProjectCreate) -> tuple[Project, Role]:
        access = await resolve_workspace(self.session, self.ctx, workspace_id)
        access.require(Role.MEMBER)
        slug = data.slug or slugify(data.name)
        if await self.session.scalar(
            select(Project.id).where(Project.workspace_id == workspace_id, Project.slug == slug)
        ):
            raise Conflict(f"Project slug '{slug}' already exists in this workspace", code="slug_taken")
        project = Project(
            workspace_id=workspace_id,
            name=data.name,
            slug=slug,
            description=data.description,
            settings_json=data.settings_json,
            created_by=self.ctx.user_id,
            updated_by=self.ctx.user_id,
        )
        self.session.add(project)
        await self.session.flush()
        await self.session.refresh(project)
        await audit.record(
            self.session,
            action="project.created",
            entity_type="project",
            entity_id=project.id,
            organization_id=access.workspace.organization_id,
            actor_user_id=self.ctx.user_id,
            after=_snapshot(project),
            request_id=self.ctx.request_id,
            ip_address=self.ctx.ip_address,
        )
        return project, access.role

    async def get(self, project_id: uuid.UUID) -> ProjectAccess:
        return await resolve_project(self.session, self.ctx, project_id)

    async def update(self, project_id: uuid.UUID, data: ProjectUpdate) -> ProjectAccess:
        access = await self.get(project_id)
        access.require(Role.MEMBER)
        project = access.project
        before = _snapshot(project)
        for field_name, value in data.model_dump(exclude_unset=True).items():
            setattr(project, field_name, value)
        project.updated_by = self.ctx.user_id
        await self.session.flush()
        await self.session.refresh(project)
        await audit.record(
            self.session,
            action="project.updated",
            entity_type="project",
            entity_id=project.id,
            organization_id=access.workspace.organization_id,
            actor_user_id=self.ctx.user_id,
            before=before,
            after=_snapshot(project),
            request_id=self.ctx.request_id,
            ip_address=self.ctx.ip_address,
        )
        return access

    # ------------------------------------------------------------------ rules
    async def list_rules(self, project_id: uuid.UUID) -> list[ProjectRule]:
        await self.get(project_id)
        return list(
            (
                await self.session.scalars(
                    select(ProjectRule)
                    .where(ProjectRule.project_id == project_id)
                    .order_by(ProjectRule.priority, ProjectRule.created_at)
                )
            ).all()
        )

    async def create_rule(self, project_id: uuid.UUID, data: ProjectRuleCreate) -> ProjectRule:
        access = await self.get(project_id)
        access.require(Role.MEMBER)
        rule = ProjectRule(
            project_id=project_id,
            created_by=self.ctx.user_id,
            updated_by=self.ctx.user_id,
            **data.model_dump(),
        )
        self.session.add(rule)
        await self.session.flush()
        await self.session.refresh(rule)
        await audit.record(
            self.session,
            action="project_rule.created",
            entity_type="project_rule",
            entity_id=rule.id,
            organization_id=access.workspace.organization_id,
            actor_user_id=self.ctx.user_id,
            after=data.model_dump(),
            request_id=self.ctx.request_id,
        )
        return rule

    async def update_rule(
        self, project_id: uuid.UUID, rule_id: uuid.UUID, data: ProjectRuleUpdate
    ) -> ProjectRule:
        access = await self.get(project_id)
        access.require(Role.MEMBER)
        rule = await self.session.scalar(
            select(ProjectRule).where(ProjectRule.id == rule_id, ProjectRule.project_id == project_id)
        )
        if rule is None:
            raise NotFound("Rule not found", code="rule_not_found")
        before = {
            "name": rule.name,
            "rule_text": rule.rule_text,
            "priority": rule.priority,
            "is_active": rule.is_active,
        }
        for field_name, value in data.model_dump(exclude_unset=True).items():
            setattr(rule, field_name, value)
        rule.updated_by = self.ctx.user_id
        await self.session.flush()
        await self.session.refresh(rule)
        await audit.record(
            self.session,
            action="project_rule.updated",
            entity_type="project_rule",
            entity_id=rule.id,
            organization_id=access.workspace.organization_id,
            actor_user_id=self.ctx.user_id,
            before=before,
            after={
                "name": rule.name,
                "rule_text": rule.rule_text,
                "priority": rule.priority,
                "is_active": rule.is_active,
            },
            request_id=self.ctx.request_id,
        )
        return rule
