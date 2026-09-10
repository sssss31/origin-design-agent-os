"""Login, token rotation, logout and first-admin bootstrap."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import Conflict, Unauthorized
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_token,
    password_needs_rehash,
    verify_password,
)
from app.domain.roles import Role
from app.domain.slugs import slugify
from app.models.identity import Organization, OrganizationMember, RefreshToken, User
from app.services import audit


@dataclass(frozen=True, slots=True)
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int


class AuthService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    # ------------------------------------------------------------------ users
    async def create_user(self, *, email: str, password: str, display_name: str | None = None) -> User:
        email = email.strip().lower()
        if await self.session.scalar(select(User.id).where(User.email == email)):
            raise Conflict("A user with this email already exists", code="email_taken")
        user = User(
            email=email,
            password_hash=hash_password(password),
            display_name=display_name or email.split("@")[0],
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def bootstrap_admin(
        self, *, email: str, password: str, organization_name: str
    ) -> tuple[User, Organization, bool]:
        """Idempotent: creates org + admin on first run, otherwise ensures the admin membership."""
        email = email.strip().lower()
        user = await self.session.scalar(select(User).where(User.email == email))
        created = False
        if user is None:
            user = await self.create_user(email=email, password=password, display_name="Administrator")
            created = True
        slug = slugify(organization_name)
        org = await self.session.scalar(select(Organization).where(Organization.slug == slug))
        if org is None:
            org = Organization(name=organization_name, slug=slug)
            self.session.add(org)
            await self.session.flush()
        membership = await self.session.scalar(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == org.id, OrganizationMember.user_id == user.id
            )
        )
        if membership is None:
            self.session.add(OrganizationMember(organization_id=org.id, user_id=user.id, role=Role.ADMIN))
        elif membership.role != Role.ADMIN:
            membership.role = Role.ADMIN
        await self.session.flush()
        if created:
            await audit.record(
                self.session,
                action="user.bootstrapped",
                entity_type="user",
                entity_id=user.id,
                organization_id=org.id,
                actor_user_id=user.id,
                after={"email": email, "role": Role.ADMIN},
            )
        return user, org, created

    # ------------------------------------------------------------------ tokens
    async def login(self, *, email: str, password: str, user_agent: str | None, ip: str | None) -> TokenPair:
        user = await self.session.scalar(select(User).where(User.email == email.strip().lower()))
        if user is None or not verify_password(user.password_hash, password):
            # Same error for unknown email and wrong password (no account enumeration).
            raise Unauthorized("Invalid email or password", code="invalid_credentials")
        if not user.is_active:
            raise Unauthorized("Account is disabled", code="account_disabled")
        if password_needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)
        user.last_login_at = datetime.now(UTC)
        return await self._issue(user, user_agent=user_agent, ip=ip)

    async def refresh(self, *, refresh_token: str, user_agent: str | None, ip: str | None) -> TokenPair:
        row = await self.session.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == hash_token(refresh_token))
        )
        now = datetime.now(UTC)
        if row is None:
            raise Unauthorized("Invalid refresh token", code="invalid_refresh_token")
        if row.revoked_at is not None:
            # Reuse of a rotated token: assume theft, revoke the whole family for this user.
            await self.session.execute(
                update(RefreshToken)
                .where(RefreshToken.user_id == row.user_id, RefreshToken.revoked_at.is_(None))
                .values(revoked_at=now)
            )
            await self.session.commit()  # the request fails, but the revocation must persist
            raise Unauthorized(
                "Refresh token reuse detected; please sign in again", code="refresh_token_reused"
            )
        if row.expires_at < now:
            raise Unauthorized("Refresh token expired", code="refresh_token_expired")
        user = await self.session.get(User, row.user_id)
        if user is None or not user.is_active:
            raise Unauthorized("Account is disabled", code="account_disabled")
        pair, new_row = await self._issue_with_row(user, user_agent=user_agent, ip=ip)
        row.revoked_at = now
        row.replaced_by_id = new_row.id
        return pair

    async def logout(self, *, refresh_token: str) -> None:
        await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.token_hash == hash_token(refresh_token), RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )

    async def revoke_all(self, user_id: uuid.UUID) -> None:
        await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )

    async def _issue(self, user: User, *, user_agent: str | None, ip: str | None) -> TokenPair:
        pair, _ = await self._issue_with_row(user, user_agent=user_agent, ip=ip)
        return pair

    async def _issue_with_row(
        self, user: User, *, user_agent: str | None, ip: str | None
    ) -> tuple[TokenPair, RefreshToken]:
        raw = generate_refresh_token()
        row = RefreshToken(
            user_id=user.id,
            token_hash=hash_token(raw),
            expires_at=datetime.now(UTC) + timedelta(days=self.settings.refresh_token_ttl_days),
            user_agent=(user_agent or "")[:300] or None,
            ip_address=ip,
        )
        self.session.add(row)
        await self.session.flush()
        access = create_access_token(subject=str(user.id), settings=self.settings)
        return TokenPair(access, raw, self.settings.access_token_ttl_minutes * 60), row
