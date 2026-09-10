from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.authz import AuthContext, require_org_role
from app.domain.roles import Role

AdminAuth = Annotated[AuthContext, Depends(require_org_role(Role.ADMIN))]


def admin_router() -> APIRouter:
    from app.api.v1.admin import agents, providers, skills, tools

    router = APIRouter(prefix="/admin", tags=["admin"])
    router.include_router(providers.router)
    router.include_router(tools.router)
    router.include_router(skills.router)
    router.include_router(agents.router)
    return router
