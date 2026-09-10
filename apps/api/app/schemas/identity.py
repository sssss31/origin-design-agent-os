from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.domain.roles import Role
from app.schemas.common import ORMModel


class UserOut(ORMModel):
    id: uuid.UUID
    email: str
    display_name: str
    is_active: bool
    created_at: datetime


class MembershipOut(BaseModel):
    organization_id: uuid.UUID
    organization_name: str
    organization_slug: str
    role: Role


class MeResponse(BaseModel):
    user: UserOut
    memberships: list[MembershipOut]
    active_organization_id: uuid.UUID | None
    capabilities: dict[str, bool]
