"""Non-admin agent endpoints: what every member needs to use the chat."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.authz import DB, Auth
from app.schemas.admin import CommandOut
from app.services.admin_serializers import command_out
from app.services.agents import list_commands

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("/commands", response_model=list[CommandOut])
async def commands(ctx: Auth, session: DB) -> list[CommandOut]:
    """Active slash commands in the caller's organization (composer autocomplete, spec §14)."""
    org_id = ctx.require_organization()
    return [command_out(a) for a in await list_commands(session, org_id)]
