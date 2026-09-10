"""Skills with draft/publish/rollback (spec §5)."""

from __future__ import annotations

import hashlib
import uuid

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.authz import AuthContext
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.db.base import utcnow
from app.domain.slugs import slugify
from app.models.skills import Skill, SkillFile, SkillVersion
from app.models.tools import Tool
from app.ports.storage import ObjectStorage
from app.schemas.admin import PublishRequest, SkillCreate, SkillUpdate, SkillVersionInput
from app.services import audit

VERSION_FIELDS = (
    "instructions",
    "variables_schema",
    "variables_defaults",
    "tool_requirements",
    "default_priority",
)


class SkillService:
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
            entity_type="skill",
            entity_id=entity_id,
            organization_id=self.org_id,
            actor_user_id=self.ctx.user_id,
            before=before,
            after=after,
            request_id=self.ctx.request_id,
            ip_address=self.ctx.ip_address,
        )

    def _query(self) -> Select[tuple[Skill]]:
        return (
            select(Skill)
            .options(selectinload(Skill.versions).selectinload(SkillVersion.files))
            .where(Skill.organization_id == self.org_id)
        )

    async def list(self) -> list[Skill]:
        return list((await self.session.scalars(self._query().order_by(Skill.name))).all())

    async def get(self, skill_id: uuid.UUID) -> Skill:
        row = await self.session.scalar(
            self._query().where(Skill.id == skill_id).execution_options(populate_existing=True)
        )
        if row is None:
            raise NotFound("Skill not found", code="skill_not_found")
        return row

    @staticmethod
    def draft_of(skill: Skill) -> SkillVersion | None:
        return next((v for v in skill.versions if v.published_at is None), None)

    @staticmethod
    def active_of(skill: Skill) -> SkillVersion | None:
        return next((v for v in skill.versions if v.id == skill.active_version_id), None)

    async def create(self, data: SkillCreate) -> Skill:
        slug = data.slug or slugify(data.name)
        if await self.session.scalar(
            select(Skill.id).where(Skill.organization_id == self.org_id, Skill.slug == slug)
        ):
            raise Conflict(f"Skill slug '{slug}' already exists", code="slug_taken")
        skill = Skill(
            organization_id=self.org_id,
            name=data.name,
            slug=slug,
            description=data.description,
            scope=data.scope,
            workspace_id=data.workspace_id,
            status="draft",
            created_by=self.ctx.user_id,
            updated_by=self.ctx.user_id,
        )
        self.session.add(skill)
        await self.session.flush()
        version = SkillVersion(skill_id=skill.id, version=1, created_by=self.ctx.user_id)
        self._apply(version, data.version)
        self.session.add(version)
        await self.session.flush()
        await self._audit(
            "skill.created", skill.id, after={"name": skill.name, "slug": slug, "scope": skill.scope}
        )
        return await self.get(skill.id)

    async def update(self, skill_id: uuid.UUID, data: SkillUpdate) -> Skill:
        skill = await self.get(skill_id)
        before = {
            "name": skill.name,
            "description": skill.description,
            "scope": skill.scope,
            "status": skill.status,
        }
        changes = data.model_dump(exclude_unset=True)
        if changes.get("status") == "active" and skill.active_version_id is None:
            raise ValidationFailed(
                "Publish a version before activating the skill", code="no_published_version"
            )
        for k, v in changes.items():
            setattr(skill, k, v)
        skill.updated_by = self.ctx.user_id
        await self.session.flush()
        await self._audit(
            "skill.updated",
            skill.id,
            before=before,
            after={
                "name": skill.name,
                "description": skill.description,
                "scope": skill.scope,
                "status": skill.status,
            },
        )
        return await self.get(skill.id)

    @staticmethod
    def _apply(version: SkillVersion, data: SkillVersionInput) -> None:
        for k, v in data.model_dump(exclude_unset=True).items():
            if v is not None:
                setattr(version, k, v)

    async def _ensure_draft(self, skill: Skill) -> SkillVersion:
        draft = self.draft_of(skill)
        if draft is not None:
            return draft
        active = self.active_of(skill)
        draft = SkillVersion(
            skill_id=skill.id,
            version=max((v.version for v in skill.versions), default=0) + 1,
            instructions=active.instructions if active else "",
            variables_schema=dict(active.variables_schema) if active else {},
            variables_defaults=dict(active.variables_defaults) if active else {},
            tool_requirements=list(active.tool_requirements) if active else [],
            default_priority=active.default_priority if active else 100,
            created_by=self.ctx.user_id,
        )
        self.session.add(draft)
        await self.session.flush()
        for f in active.files if active else []:
            self.session.add(
                SkillFile(
                    skill_version_id=draft.id,
                    filename=f.filename,
                    storage_key=f.storage_key,
                    mime_type=f.mime_type,
                    size_bytes=f.size_bytes,
                    checksum_sha256=f.checksum_sha256,
                    description=f.description,
                    created_by=self.ctx.user_id,
                )
            )
        await self.session.flush()
        self.session.expire(skill, ["versions"])
        return draft

    async def save_draft(self, skill_id: uuid.UUID, data: SkillVersionInput) -> Skill:
        skill = await self.get(skill_id)
        draft = await self._ensure_draft(skill)
        self._apply(draft, data)
        skill.updated_by = self.ctx.user_id
        await self.session.flush()
        await self._audit(
            "skill.draft_saved",
            skill.id,
            after={"version": draft.version, **data.model_dump(exclude_unset=True, exclude_none=True)},
        )
        return await self.get(skill.id)

    async def _validate(self, version: SkillVersion) -> None:
        problems: list[str] = []
        if not version.instructions.strip():
            problems.append("instructions must not be empty")
        if version.tool_requirements:
            rows = await self.session.scalars(
                select(Tool.slug).where(
                    Tool.organization_id == self.org_id, Tool.slug.in_(version.tool_requirements)
                )
            )
            missing = set(version.tool_requirements) - set(rows.all())
            if missing:
                problems.append(f"unknown tool requirements: {sorted(missing)}")
        if problems:
            raise ValidationFailed(
                "Skill cannot be published", code="publish_validation_failed", details=problems
            )

    async def publish(self, skill_id: uuid.UUID, data: PublishRequest) -> Skill:
        skill = await self.get(skill_id)
        before = {"active_version_id": str(skill.active_version_id), "status": skill.status}
        if data.version_id is not None:  # rollback / re-activate a published version
            target = next((v for v in skill.versions if v.id == data.version_id), None)
            if target is None or target.published_at is None:
                raise ValidationFailed(
                    "version_id must reference a published version of this skill", code="invalid_version"
                )
            action = "skill.rolled_back"
        else:
            target = self.draft_of(skill)
            if target is None:
                raise ValidationFailed("Nothing to publish: no draft version", code="no_draft")
            await self._validate(target)
            target.published_at = utcnow()
            if data.change_note:
                target.change_note = data.change_note
            action = "skill.published"
        skill.active_version_id = target.id
        skill.status = "active"
        skill.updated_by = self.ctx.user_id
        await self.session.flush()
        await self._audit(
            action,
            skill.id,
            before=before,
            after={"active_version_id": str(target.id), "version": target.version, "status": "active"},
        )
        return await self.get(skill.id)

    async def add_file(
        self,
        skill_id: uuid.UUID,
        *,
        filename: str,
        data: bytes,
        mime_type: str,
        description: str | None,
        storage: ObjectStorage,
    ) -> Skill:
        skill = await self.get(skill_id)
        draft = await self._ensure_draft(skill)
        safe_name = filename.replace("/", "_").replace("\\", "_")[:255] or "file"
        key = f"org/{self.org_id}/skills/{skill.id}/v{draft.version}/{uuid.uuid4().hex}-{safe_name}"
        stored = await storage.put(key, data, content_type=mime_type)
        self.session.add(
            SkillFile(
                skill_version_id=draft.id,
                filename=safe_name,
                storage_key=stored.key,
                mime_type=mime_type,
                size_bytes=stored.size,
                checksum_sha256=hashlib.sha256(data).hexdigest(),
                description=description,
                created_by=self.ctx.user_id,
            )
        )
        await self.session.flush()
        self.session.expire(skill, ["versions"])
        await self._audit(
            "skill.file_added",
            skill.id,
            after={"version": draft.version, "filename": safe_name, "size": stored.size},
        )
        return await self.get(skill.id)
