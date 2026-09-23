"""Admin → Users and Admin → System Settings (spec §18)."""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.admin import AdminAuth
from app.core.authz import DB, Config
from app.core.config import Settings
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.domain.roles import Role
from app.models.identity import Organization, OrganizationMember, User
from app.models.workflows import ApiUsage
from app.schemas.common import Email
from app.services import audit
from app.services.auth import AuthService

router = APIRouter()


# ----------------------------------------------------------------------------- users
class MemberOut(BaseModel):
    user_id: uuid.UUID
    email: str
    display_name: str
    role: Role
    is_active: bool
    last_login_at: datetime | None
    joined_at: datetime
    requests_30d: int = 0
    cost_30d_usd: float = 0.0


class MemberInvite(BaseModel):
    email: Email
    display_name: str | None = Field(default=None, max_length=120)
    role: Role = Role.MEMBER


class MemberInvited(BaseModel):
    member: MemberOut
    temporary_password: str | None = Field(default=None, description="Shown once; the user must change it.")


class MemberUpdate(BaseModel):
    role: Role | None = None
    is_active: bool | None = None


async def _member_out(session: AsyncSession, org_id: uuid.UUID, m: OrganizationMember, u: User) -> MemberOut:
    from datetime import UTC, timedelta

    since = datetime.now(UTC) - timedelta(days=30)
    row = (
        await session.execute(
            select(
                func.coalesce(func.sum(ApiUsage.requests), 0),
                func.coalesce(func.sum(ApiUsage.estimated_cost_usd), 0),
            ).where(
                ApiUsage.organization_id == org_id, ApiUsage.user_id == u.id, ApiUsage.created_at >= since
            )
        )
    ).one()
    return MemberOut(
        user_id=u.id,
        email=u.email,
        display_name=u.display_name,
        role=Role(m.role),
        is_active=u.is_active,
        last_login_at=u.last_login_at,
        joined_at=m.created_at,
        requests_30d=int(row[0]),
        cost_30d_usd=round(float(row[1]), 4),
    )


@router.get("/users", response_model=list[MemberOut])
async def list_users(ctx: AdminAuth, session: DB) -> list[MemberOut]:
    org_id = ctx.require_organization()
    rows = (
        await session.execute(
            select(OrganizationMember, User)
            .join(User, User.id == OrganizationMember.user_id)
            .where(OrganizationMember.organization_id == org_id)
            .order_by(User.email)
        )
    ).all()
    return [await _member_out(session, org_id, m, u) for m, u in rows]


@router.post("/users", response_model=MemberInvited, status_code=status.HTTP_201_CREATED)
async def invite_user(body: MemberInvite, ctx: AdminAuth, session: DB, settings: Config) -> MemberInvited:
    """Add a member. New accounts get a one-time temporary password (no e-mail provider in V0)."""
    org_id = ctx.require_organization()
    email = body.email
    user = await session.scalar(select(User).where(User.email == email))
    temp: str | None = None
    if user is None:
        temp = secrets.token_urlsafe(12)
        user = await AuthService(session, settings).create_user(
            email=email, password=temp, display_name=body.display_name
        )
    existing = await session.scalar(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id, OrganizationMember.user_id == user.id
        )
    )
    if existing is not None:
        raise Conflict("User is already a member of this organization", code="already_member")
    member = OrganizationMember(organization_id=org_id, user_id=user.id, role=body.role)
    session.add(member)
    await session.flush()
    await audit.record(
        session,
        action="user.invited",
        entity_type="organization_member",
        entity_id=member.id,
        organization_id=org_id,
        actor_user_id=ctx.user_id,
        after={"email": email, "role": body.role, "new_account": temp is not None},
        request_id=ctx.request_id,
        ip_address=ctx.ip_address,
    )
    return MemberInvited(member=await _member_out(session, org_id, member, user), temporary_password=temp)


@router.patch("/users/{user_id}", response_model=MemberOut)
async def update_user(
    user_id: uuid.UUID, body: MemberUpdate, ctx: AdminAuth, session: DB, settings: Config
) -> MemberOut:
    org_id = ctx.require_organization()
    row = (
        await session.execute(
            select(OrganizationMember, User)
            .join(User, User.id == OrganizationMember.user_id)
            .where(OrganizationMember.organization_id == org_id, OrganizationMember.user_id == user_id)
        )
    ).first()
    if row is None:
        raise NotFound("Member not found", code="member_not_found")
    member, user = row
    before = {"role": member.role, "is_active": user.is_active}
    if body.role is not None and body.role != Role.ADMIN and member.role == Role.ADMIN:
        admins = await session.scalar(
            select(func.count(OrganizationMember.id)).where(
                OrganizationMember.organization_id == org_id, OrganizationMember.role == Role.ADMIN
            )
        )
        if (admins or 0) <= 1:
            raise ValidationFailed("The organization needs at least one admin", code="last_admin")
    if body.role is not None:
        member.role = body.role
    if body.is_active is not None:
        if user.id == ctx.user_id and body.is_active is False:
            raise ValidationFailed("You cannot deactivate your own account", code="self_deactivate")
        user.is_active = body.is_active
        if not body.is_active:
            await AuthService(session, settings).revoke_all(user.id)
    await session.flush()
    await audit.record(
        session,
        action="user.updated",
        entity_type="organization_member",
        entity_id=member.id,
        organization_id=org_id,
        actor_user_id=ctx.user_id,
        before=before,
        after={"role": member.role, "is_active": user.is_active},
        request_id=ctx.request_id,
        ip_address=ctx.ip_address,
    )
    return await _member_out(session, org_id, member, user)


# ----------------------------------------------------------------------------- system settings
class SystemSettingsOut(BaseModel):
    organization_id: uuid.UUID
    name: str
    global_rules: str | None
    display_currency: str
    fx_usd_rate: float
    quota_runs_per_day: int
    default_max_revisions: int
    default_provider_type: str | None
    outbound: dict[str, Any]
    environment: str


class SystemSettingsIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    global_rules: str | None = Field(default=None, max_length=20000)
    display_currency: Literal["INR", "USD", "EUR", "GBP"] | None = None
    fx_usd_rate: float | None = Field(default=None, gt=0, le=100000)
    quota_runs_per_day: int | None = Field(default=None, ge=0, le=1_000_000)
    default_max_revisions: int | None = Field(default=None, ge=0, le=5)


def _settings_out(org: Organization, settings: Settings) -> SystemSettingsOut:
    s = org.settings_json or {}
    return SystemSettingsOut(
        organization_id=org.id,
        name=org.name,
        global_rules=org.global_rules,
        display_currency=str(s.get("display_currency", "INR")),
        fx_usd_rate=float(s.get("fx_usd_rate", 83.0)),
        quota_runs_per_day=int(s.get("quota_runs_per_day", settings.default_runs_per_day)),
        default_max_revisions=int(s.get("default_max_revisions", settings.default_max_revisions)),
        default_provider_type=s.get("default_provider_type"),
        outbound={
            "allow_http": settings.outbound_allow_http,
            "allowed_hosts": settings.outbound_allowed_hosts_list,
            "max_response_bytes": settings.outbound_max_response_bytes,
            "default_timeout_seconds": settings.outbound_default_timeout_seconds,
            "provider_retry_attempts": settings.provider_retry_attempts,
        },
        environment=settings.app_env,
    )


@router.get("/settings", response_model=SystemSettingsOut)
async def get_settings_view(ctx: AdminAuth, session: DB, settings: Config) -> SystemSettingsOut:
    org = await session.get(Organization, ctx.require_organization())
    assert org is not None
    return _settings_out(org, settings)


@router.put("/settings", response_model=SystemSettingsOut)
async def update_settings(
    body: SystemSettingsIn, ctx: AdminAuth, session: DB, settings: Config
) -> SystemSettingsOut:
    org = await session.get(Organization, ctx.require_organization())
    assert org is not None
    before = _settings_out(org, settings).model_dump(mode="json")
    changes = body.model_dump(exclude_unset=True)
    if "name" in changes and changes["name"]:
        org.name = changes["name"]
    if "global_rules" in changes:
        org.global_rules = changes["global_rules"]
    merged = dict(org.settings_json or {})
    for key in ("display_currency", "fx_usd_rate", "quota_runs_per_day", "default_max_revisions"):
        if key in changes and changes[key] is not None:
            merged[key] = changes[key]
    org.settings_json = merged
    await session.flush()
    after = _settings_out(org, settings).model_dump(mode="json")
    await audit.record(
        session,
        action="settings.updated",
        entity_type="organization",
        entity_id=org.id,
        organization_id=org.id,
        actor_user_id=ctx.user_id,
        before={k: before[k] for k in changes if k in before},
        after={k: after[k] for k in changes if k in after},
        request_id=ctx.request_id,
        ip_address=ctx.ip_address,
    )
    return _settings_out(org, settings)
