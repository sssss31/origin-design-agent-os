from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile, status

from app.api.v1.admin import AdminAuth
from app.core.authz import DB, Config
from app.core.deps import AdaptersDep
from app.core.errors import ValidationFailed
from app.schemas.admin import (
    AgentTestOut,
    PublishRequest,
    SkillCreate,
    SkillOut,
    SkillTestRequest,
    SkillUpdate,
    SkillVersionInput,
)
from app.services.admin_serializers import skill_out
from app.services.skills import SkillService

router = APIRouter(prefix="/skills")

ALLOWED_KNOWLEDGE_TYPES = {
    "text/plain",
    "text/markdown",
    "application/json",
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/svg+xml",
    "text/csv",
}


@router.get("", response_model=list[SkillOut])
async def list_skills(ctx: AdminAuth, session: DB) -> list[SkillOut]:
    return [skill_out(s) for s in await SkillService(session, ctx).list()]


@router.post("", response_model=SkillOut, status_code=status.HTTP_201_CREATED)
async def create_skill(body: SkillCreate, ctx: AdminAuth, session: DB) -> SkillOut:
    return skill_out(await SkillService(session, ctx).create(body))


@router.get("/{skill_id}", response_model=SkillOut)
async def get_skill(skill_id: uuid.UUID, ctx: AdminAuth, session: DB) -> SkillOut:
    return skill_out(await SkillService(session, ctx).get(skill_id))


@router.patch("/{skill_id}", response_model=SkillOut)
async def update_skill(skill_id: uuid.UUID, body: SkillUpdate, ctx: AdminAuth, session: DB) -> SkillOut:
    return skill_out(await SkillService(session, ctx).update(skill_id, body))


@router.post("/{skill_id}/versions", response_model=SkillOut)
async def save_skill_draft(
    skill_id: uuid.UUID, body: SkillVersionInput, ctx: AdminAuth, session: DB
) -> SkillOut:
    """Create or update the draft version (editing an active skill never mutates the published version)."""
    return skill_out(await SkillService(session, ctx).save_draft(skill_id, body))


@router.post("/{skill_id}/publish", response_model=SkillOut)
async def publish_skill(skill_id: uuid.UUID, body: PublishRequest, ctx: AdminAuth, session: DB) -> SkillOut:
    return skill_out(await SkillService(session, ctx).publish(skill_id, body))


@router.post("/{skill_id}/test", response_model=AgentTestOut)
async def test_skill(
    skill_id: uuid.UUID, body: SkillTestRequest, ctx: AdminAuth, session: DB, adapters: AdaptersDep
) -> AgentTestOut:
    """Sandbox: run the chosen agent with this skill's draft/active version injected (spec §5 step 6)."""
    return await SkillService(session, ctx).test(skill_id, body, adapters)


@router.post("/{skill_id}/files", response_model=SkillOut, status_code=status.HTTP_201_CREATED)
async def upload_skill_file(
    skill_id: uuid.UUID,
    ctx: AdminAuth,
    session: DB,
    adapters: AdaptersDep,
    settings: Config,
    file: Annotated[UploadFile, File()],
    description: Annotated[str | None, Form()] = None,
) -> SkillOut:
    content_type = (file.content_type or "application/octet-stream").split(";")[0].strip()
    if content_type not in ALLOWED_KNOWLEDGE_TYPES:
        raise ValidationFailed(f"file type {content_type} is not allowed", code="unsupported_file_type")
    data = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise ValidationFailed(f"file exceeds {settings.max_upload_mb} MB", code="file_too_large")
    skill = await SkillService(session, ctx).add_file(
        skill_id,
        filename=file.filename or "file",
        data=data,
        mime_type=content_type,
        description=description,
        storage=adapters.storage,
    )
    return skill_out(skill)
