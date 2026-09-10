from __future__ import annotations

from fastapi import APIRouter

from app.core.authz import Auth
from app.schemas.identity import MembershipOut, MeResponse, UserOut

router = APIRouter(tags=["me"])


@router.get("/me", response_model=MeResponse)
async def me(ctx: Auth) -> MeResponse:
    memberships = [
        MembershipOut(
            organization_id=org_id,
            organization_name=ctx.organizations[org_id].name,
            organization_slug=ctx.organizations[org_id].slug,
            role=role,
        )
        for org_id, role in ctx.memberships.items()
    ]
    return MeResponse(
        user=UserOut.model_validate(ctx.user),
        memberships=memberships,
        active_organization_id=ctx.organization_id,
        capabilities={"admin_console": ctx.is_any_admin},
    )
