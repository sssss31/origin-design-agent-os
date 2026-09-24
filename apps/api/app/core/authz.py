"""Authentication + organization-scoped authorization dependencies.

`AuthContext` is passed into every service call so that every query is tenant-scoped
(spec §17: never trust IDs from the client without authorization checks).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Annotated

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import Forbidden, Unauthorized, ValidationFailed
from app.core.security import TokenError, decode_access_token
from app.db.session import get_session
from app.domain.roles import Role, has_at_least
from app.models.identity import Organization, OrganizationMember, User

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(slots=True)
class AuthContext:
    user: User
    memberships: dict[uuid.UUID, Role] = field(default_factory=dict)
    organizations: dict[uuid.UUID, Organization] = field(default_factory=dict)
    organization_id: uuid.UUID | None = None
    request_id: str | None = None
    ip_address: str | None = None

    @property
    def user_id(self) -> uuid.UUID:
        return self.user.id

    @property
    def organization_role(self) -> Role | None:
        return self.memberships.get(self.organization_id) if self.organization_id else None

    def role_in(self, organization_id: uuid.UUID) -> Role | None:
        return self.memberships.get(organization_id)

    def is_org_admin(self, organization_id: uuid.UUID) -> bool:
        return self.memberships.get(organization_id) == Role.ADMIN

    @property
    def is_any_admin(self) -> bool:
        return any(r == Role.ADMIN for r in self.memberships.values())

    def require_organization(self, explicit: uuid.UUID | None = None) -> uuid.UUID:
        org_id = explicit or self.organization_id
        if org_id is None:
            if len(self.memberships) == 1:
                return next(iter(self.memberships))
            raise ValidationFailed(
                "Organization is ambiguous; pass X-Organization-Id or organization_id",
                code="organization_required",
            )
        if org_id not in self.memberships:
            raise Forbidden("Not a member of this organization", code="not_a_member")
        return org_id


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(current_settings)],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise Unauthorized("Missing bearer token", code="missing_token")
    try:
        payload = decode_access_token(credentials.credentials, settings)
        user_id = uuid.UUID(payload["sub"])
    except (TokenError, ValueError, KeyError) as exc:
        raise Unauthorized("Invalid or expired token", code="invalid_token") from exc
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise Unauthorized("Account not found or disabled", code="account_disabled")
    request.state.user_id = user.id
    return user


async def get_auth_context(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    x_organization_id: Annotated[uuid.UUID | None, Header(alias="X-Organization-Id")] = None,
) -> AuthContext:
    rows = (
        await session.execute(
            select(OrganizationMember, Organization)
            .join(Organization, Organization.id == OrganizationMember.organization_id)
            .where(OrganizationMember.user_id == user.id)
        )
    ).all()
    memberships = {m.organization_id: Role(m.role) for m, _ in rows}
    organizations = {o.id: o for _, o in rows}
    organization_id: uuid.UUID | None = None
    if x_organization_id is not None:
        if x_organization_id not in memberships:
            raise Forbidden("Not a member of this organization", code="not_a_member")
        organization_id = x_organization_id
    elif len(memberships) == 1:
        organization_id = next(iter(memberships))
    client = request.client
    return AuthContext(
        user=user,
        memberships=memberships,
        organizations=organizations,
        organization_id=organization_id,
        request_id=getattr(request.state, "request_id", None),
        ip_address=client.host if client else None,
    )


def require_org_role(required: Role):
    """Dependency factory: the caller must hold `required` (or higher) in the active organization."""

    async def _dep(ctx: Annotated[AuthContext, Depends(get_auth_context)]) -> AuthContext:
        org_id = ctx.require_organization()
        if not has_at_least(ctx.memberships.get(org_id), required):
            raise Forbidden(f"Requires {required} role", code="insufficient_role")
        ctx.organization_id = org_id
        return ctx

    return _dep


CurrentUser = Annotated[User, Depends(get_current_user)]
Auth = Annotated[AuthContext, Depends(get_auth_context)]
DB = Annotated[AsyncSession, Depends(get_session)]


def current_settings(request: Request) -> Settings:
    """The settings the app was created with (create_app(settings)); falls back to the env-based
    singleton so plain scripts keep working."""
    return getattr(request.app.state, "settings", None) or get_settings()


Config = Annotated[Settings, Depends(current_settings)]
