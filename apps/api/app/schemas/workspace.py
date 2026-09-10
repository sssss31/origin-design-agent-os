from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.domain.roles import Role
from app.schemas.common import Email, ORMModel

Slug = Field(default=None, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=80)


class WorkspaceCreate(BaseModel):
    organization_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=160)
    slug: str | None = Slug
    description: str | None = Field(default=None, max_length=2000)
    brand_config: dict[str, Any] = Field(default_factory=dict)
    rules_text: str | None = Field(default=None, max_length=20000)


class WorkspaceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    brand_config: dict[str, Any] | None = None
    rules_text: str | None = Field(default=None, max_length=20000)
    status: str | None = Field(default=None, pattern="^(active|archived)$")


class WorkspaceOut(ORMModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    slug: str
    description: str | None
    status: str
    brand_config: dict[str, Any]
    rules_text: str | None
    created_at: datetime
    updated_at: datetime
    my_role: Role


class WorkspaceMemberOut(BaseModel):
    user_id: uuid.UUID
    email: str
    display_name: str
    role: Role


class WorkspaceMemberAdd(BaseModel):
    email: Email
    role: Role = Role.MEMBER


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    slug: str | None = Slug
    description: str | None = Field(default=None, max_length=2000)
    settings_json: dict[str, Any] = Field(default_factory=dict)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    settings_json: dict[str, Any] | None = None
    summary_text: str | None = Field(default=None, max_length=20000)
    status: str | None = Field(default=None, pattern="^(active|archived)$")


class ProjectOut(ORMModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    slug: str
    description: str | None
    status: str
    summary_text: str | None
    settings_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    my_role: Role


class ProjectRuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    rule_text: str = Field(min_length=1, max_length=20000)
    priority: int = Field(default=100, ge=0, le=10000)
    is_active: bool = True


class ProjectRuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    rule_text: str | None = Field(default=None, min_length=1, max_length=20000)
    priority: int | None = Field(default=None, ge=0, le=10000)
    is_active: bool | None = None


class ProjectRuleOut(ORMModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    rule_text: str
    priority: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
