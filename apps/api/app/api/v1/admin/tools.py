from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.v1.admin import AdminAuth
from app.core.authz import DB
from app.core.deps import AdaptersDep
from app.schemas.admin import ToolCreate, ToolOut, ToolPermissionIn, ToolSecretIn, ToolUpdate
from app.services.admin_serializers import tool_out
from app.services.tools import ToolService

router = APIRouter(prefix="/tools")


@router.get("", response_model=list[ToolOut])
async def list_tools(ctx: AdminAuth, session: DB) -> list[ToolOut]:
    return [tool_out(t) for t in await ToolService(session, ctx).list()]


@router.post("", response_model=ToolOut, status_code=status.HTTP_201_CREATED)
async def create_tool(body: ToolCreate, ctx: AdminAuth, session: DB) -> ToolOut:
    return tool_out(await ToolService(session, ctx).create(body))


@router.get("/{tool_id}", response_model=ToolOut)
async def get_tool(tool_id: uuid.UUID, ctx: AdminAuth, session: DB) -> ToolOut:
    return tool_out(await ToolService(session, ctx).get(tool_id))


@router.patch("/{tool_id}", response_model=ToolOut)
async def update_tool(tool_id: uuid.UUID, body: ToolUpdate, ctx: AdminAuth, session: DB) -> ToolOut:
    return tool_out(await ToolService(session, ctx).update(tool_id, body))


@router.post("/{tool_id}/secret", response_model=ToolOut)
async def set_tool_secret(
    tool_id: uuid.UUID, body: ToolSecretIn, ctx: AdminAuth, session: DB, adapters: AdaptersDep
) -> ToolOut:
    return tool_out(await ToolService(session, ctx).set_secret(tool_id, body.secret, adapters.secrets))


@router.post("/{tool_id}/permissions", response_model=ToolOut)
async def set_permission(tool_id: uuid.UUID, body: ToolPermissionIn, ctx: AdminAuth, session: DB) -> ToolOut:
    return tool_out(await ToolService(session, ctx).set_permission(tool_id, body))


@router.delete("/{tool_id}/permissions/{permission_id}", response_model=ToolOut)
async def delete_permission(
    tool_id: uuid.UUID, permission_id: uuid.UUID, ctx: AdminAuth, session: DB
) -> ToolOut:
    return tool_out(await ToolService(session, ctx).delete_permission(tool_id, permission_id))
