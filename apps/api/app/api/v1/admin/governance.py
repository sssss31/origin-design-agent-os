"""Admin audit log, usage and error views (spec §20 Admin Dashboard / Audit)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.v1.admin import AdminAuth
from app.core.authz import DB
from app.models.governance import AuditLog
from app.models.identity import User
from app.models.workflows import ApiUsage, ErrorEvent, WorkflowRun

router = APIRouter()


class AuditOut(BaseModel):
    id: uuid.UUID
    action: str
    entity_type: str
    entity_id: str | None
    actor_email: str | None
    before_json: dict | None
    after_json: dict | None
    request_id: str | None
    ip_address: str | None
    created_at: datetime


class UsageSummary(BaseModel):
    runs_today: int
    runs_failed_today: int
    error_rate: float
    input_tokens_today: int
    output_tokens_today: int
    tool_calls_today: int
    recent_errors: list[dict]


@router.get("/audit", response_model=list[AuditOut])
async def audit_log(
    ctx: AdminAuth,
    session: DB,
    limit: int = Query(default=100, ge=1, le=500),
    action: str | None = None,
    entity_type: str | None = None,
    before: datetime | None = None,
) -> list[AuditOut]:
    q = (
        select(AuditLog, User.email)
        .outerjoin(User, User.id == AuditLog.actor_user_id)
        .where(AuditLog.organization_id == ctx.organization_id)
    )
    if action:
        q = q.where(AuditLog.action.ilike(f"{action}%"))
    if entity_type:
        q = q.where(AuditLog.entity_type == entity_type)
    if before:
        q = q.where(AuditLog.created_at < before)
    rows = (await session.execute(q.order_by(AuditLog.created_at.desc()).limit(limit))).all()
    return [
        AuditOut(
            id=a.id,
            action=a.action,
            entity_type=a.entity_type,
            entity_id=a.entity_id,
            actor_email=email,
            before_json=a.before_json,
            after_json=a.after_json,
            request_id=a.request_id,
            ip_address=a.ip_address,
            created_at=a.created_at,
        )
        for a, email in rows
    ]


@router.get("/usage", response_model=UsageSummary)
async def usage(ctx: AdminAuth, session: DB) -> UsageSummary:
    since = datetime.now(UTC) - timedelta(days=1)
    org = ctx.organization_id
    runs = (
        await session.scalar(
            select(func.count(WorkflowRun.id)).where(
                WorkflowRun.organization_id == org, WorkflowRun.created_at >= since
            )
        )
        or 0
    )
    failed = (
        await session.scalar(
            select(func.count(WorkflowRun.id)).where(
                WorkflowRun.organization_id == org,
                WorkflowRun.created_at >= since,
                WorkflowRun.status == "FAILED",
            )
        )
        or 0
    )
    tokens = (
        await session.execute(
            select(
                func.coalesce(func.sum(ApiUsage.input_tokens), 0),
                func.coalesce(func.sum(ApiUsage.output_tokens), 0),
                func.coalesce(func.sum(ApiUsage.tool_calls), 0),
            ).where(ApiUsage.organization_id == org, ApiUsage.created_at >= since)
        )
    ).one()
    errors = (
        await session.scalars(
            select(ErrorEvent)
            .where(ErrorEvent.organization_id == org)
            .order_by(ErrorEvent.created_at.desc())
            .limit(10)
        )
    ).all()
    return UsageSummary(
        runs_today=runs,
        runs_failed_today=failed,
        error_rate=round(failed / runs, 3) if runs else 0.0,
        input_tokens_today=int(tokens[0]),
        output_tokens_today=int(tokens[1]),
        tool_calls_today=int(tokens[2]),
        recent_errors=[
            {
                "run_id": str(e.run_id) if e.run_id else None,
                "code": e.code,
                "message": e.message,
                "retryable": e.retryable,
                "created_at": e.created_at.isoformat(),
            }
            for e in errors
        ],
    )
