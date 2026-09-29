"""The signed-in user's profile (/me), also embedded in the login response."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.roles import Role
from app.models.identity import Organization, OrganizationMember, User
from app.schemas.identity import MembershipOut, MeResponse, UserOut


async def profile_for_email(session: AsyncSession, email: str) -> MeResponse | None:
    user = await session.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None:
        return None
    rows = (
        await session.execute(
            select(OrganizationMember, Organization)
            .join(Organization, Organization.id == OrganizationMember.organization_id)
            .where(OrganizationMember.user_id == user.id)
        )
    ).all()
    memberships = [
        MembershipOut(
            organization_id=m.organization_id,
            organization_name=o.name,
            organization_slug=o.slug,
            role=Role(m.role),
        )
        for m, o in rows
    ]
    return MeResponse(
        user=UserOut.model_validate(user),
        memberships=memberships,
        active_organization_id=memberships[0].organization_id if len(memberships) == 1 else None,
        capabilities={"admin_console": any(m.role == Role.ADMIN for m in memberships)},
    )
