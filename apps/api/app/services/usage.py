"""Usage & cost telemetry (spec §14–§15): price every provider call, enforce budgets, report.

Pricing comes from `model_pricing` rows the admin maintains (exact model id or a prefix
such as `gpt-5*`); nothing is hardcoded. Costs are stored in USD; the admin dashboard
converts to the organization's display currency using `settings_json.fx_usd_rate`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import RateLimited
from app.models.agents import Agent
from app.models.identity import Organization, User
from app.models.providers import AIProvider
from app.models.workflows import ApiUsage, ModelPricing, WorkflowRun
from app.models.workspace import Workspace
from app.providers.base import ModelPrice, UsageEstimate, estimate_cost

Breakdown = Literal["agent", "model", "user", "workspace", "workflow", "provider"]


async def price_for(
    session: AsyncSession, organization_id: uuid.UUID, provider_type: str, model: str
) -> ModelPrice | None:
    rows = (
        await session.scalars(
            select(ModelPricing).where(
                ModelPricing.organization_id == organization_id, ModelPricing.provider_type == provider_type
            )
        )
    ).all()
    exact = next((r for r in rows if r.model == model), None)
    if exact is None:
        prefixes = [r for r in rows if r.model.endswith("*") and model.startswith(r.model[:-1])]
        exact = max(prefixes, key=lambda r: len(r.model), default=None)
    if exact is None:
        return None
    return ModelPrice(
        input_per_million=float(exact.input_per_million),
        cached_input_per_million=float(exact.cached_input_per_million),
        output_per_million=float(exact.output_per_million),
        image_per_unit=float(exact.image_per_unit),
    )


@dataclass(slots=True)
class UsageContext:
    organization_id: uuid.UUID
    provider_type: str
    provider_id: uuid.UUID | None
    model: str
    run_id: uuid.UUID | None = None
    node_run_id: uuid.UUID | None = None
    agent_id: uuid.UUID | None = None
    agent_version_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    workspace_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    workflow_id: uuid.UUID | None = None
    command: str | None = None


async def record_usage(
    session: AsyncSession,
    ctx: UsageContext,
    usage: dict[str, Any],
    *,
    duration_ms: int,
    status: str = "ok",
    error_code: str | None = None,
) -> tuple[ApiUsage, UsageEstimate]:
    """Persist one provider call with its estimated cost. Never raises on missing pricing."""
    price = await price_for(session, ctx.organization_id, ctx.provider_type, ctx.model)
    est = estimate_cost(usage, price)
    row = ApiUsage(
        organization_id=ctx.organization_id,
        run_id=ctx.run_id,
        node_run_id=ctx.node_run_id,
        provider_type=ctx.provider_type,
        provider_id=ctx.provider_id,
        agent_id=ctx.agent_id,
        agent_version_id=ctx.agent_version_id,
        user_id=ctx.user_id,
        workspace_id=ctx.workspace_id,
        project_id=ctx.project_id,
        workflow_id=ctx.workflow_id,
        command=ctx.command,
        model=ctx.model,
        input_tokens=est.input_tokens,
        cached_input_tokens=est.cached_input_tokens,
        output_tokens=est.output_tokens,
        reasoning_tokens=est.reasoning_tokens,
        tool_calls=est.tool_calls,
        image_generations=est.image_generations,
        requests=int(usage.get("requests", 1) or 1),
        estimated_cost_usd=Decimal(str(est.estimated_cost_usd)),
        priced=est.priced,
        duration_ms=duration_ms,
        status=status,
        error_code=error_code,
    )
    session.add(row)
    return row, est


# ----------------------------------------------------------------------------- budgets
async def month_spend_usd(
    session: AsyncSession, organization_id: uuid.UUID, provider_id: uuid.UUID | None = None
) -> float:
    start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    q = select(func.coalesce(func.sum(ApiUsage.estimated_cost_usd), 0)).where(
        ApiUsage.organization_id == organization_id, ApiUsage.created_at >= start
    )
    if provider_id is not None:
        q = q.where(ApiUsage.provider_id == provider_id)
    return float(await session.scalar(q) or 0)


async def day_requests(session: AsyncSession, organization_id: uuid.UUID, provider_id: uuid.UUID) -> int:
    since = datetime.now(UTC) - timedelta(days=1)
    return int(
        await session.scalar(
            select(func.coalesce(func.sum(ApiUsage.requests), 0)).where(
                ApiUsage.organization_id == organization_id,
                ApiUsage.provider_id == provider_id,
                ApiUsage.created_at >= since,
            )
        )
        or 0
    )


async def enforce_provider_limits(session: AsyncSession, provider: AIProvider) -> None:
    """Raise RateLimited (429) when the provider's admin-configured limits are exhausted."""
    policy = provider.rate_limit_policy or {}
    budget = policy.get("monthly_budget_usd")
    if budget:
        spent = await month_spend_usd(session, provider.organization_id, provider.id)
        if spent >= float(budget):
            raise RateLimited(
                f"Monthly budget for provider '{provider.name}' reached "
                f"(${spent:.2f} of ${float(budget):.2f}).",
                code="provider_budget_exhausted",
            )
    per_day = policy.get("max_requests_per_day")
    if per_day:
        used = await day_requests(session, provider.organization_id, provider.id)
        if used >= int(per_day):
            raise RateLimited(
                f"Daily request limit for provider '{provider.name}' reached ({used} of {int(per_day)}).",
                code="provider_daily_limit",
            )


# ----------------------------------------------------------------------------- reporting
def _window(range_: str) -> datetime:
    now = datetime.now(UTC)
    if range_ == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if range_ == "7d":
        return now - timedelta(days=7)
    if range_ == "30d":
        return now - timedelta(days=30)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)  # month


async def summary(session: AsyncSession, organization_id: uuid.UUID) -> dict[str, Any]:
    org = await session.get(Organization, organization_id)
    settings = (org.settings_json if org else {}) or {}
    currency = str(settings.get("display_currency", "INR"))
    fx = float(settings.get("fx_usd_rate", 83.0))

    async def totals(since: datetime) -> dict[str, Any]:
        row = (
            await session.execute(
                select(
                    func.coalesce(func.sum(ApiUsage.estimated_cost_usd), 0),
                    func.coalesce(func.sum(ApiUsage.requests), 0),
                    func.coalesce(func.sum(ApiUsage.input_tokens + ApiUsage.output_tokens), 0),
                    func.coalesce(func.sum(ApiUsage.image_generations), 0),
                    func.coalesce(func.sum(ApiUsage.tool_calls), 0),
                    func.coalesce(func.sum(case((ApiUsage.priced.is_(False), 1), else_=0)), 0),
                ).where(ApiUsage.organization_id == organization_id, ApiUsage.created_at >= since)
            )
        ).one()
        cost = float(row[0])
        return {
            "cost_usd": round(cost, 4),
            "cost_display": round(cost * fx, 2),
            "requests": int(row[1]),
            "tokens": int(row[2]),
            "images": int(row[3]),
            "tool_calls": int(row[4]),
            "unpriced_calls": int(row[5]),
        }

    return {
        "currency": currency,
        "fx_usd_rate": fx,
        "today": await totals(_window("today")),
        "month": await totals(_window("month")),
        "last_30d": await totals(_window("30d")),
    }


async def breakdown(
    session: AsyncSession, organization_id: uuid.UUID, by: Breakdown, range_: str
) -> list[dict[str, Any]]:
    since = _window(range_)
    dims: dict[str, tuple[Any, Any, Any]] = {
        "agent": (ApiUsage.agent_id, Agent.name, (Agent, Agent.id == ApiUsage.agent_id)),
        "user": (ApiUsage.user_id, User.email, (User, User.id == ApiUsage.user_id)),
        "workspace": (
            ApiUsage.workspace_id,
            Workspace.name,
            (Workspace, Workspace.id == ApiUsage.workspace_id),
        ),
        "workflow": (ApiUsage.command, ApiUsage.command, None),
        "provider": (ApiUsage.provider_type, ApiUsage.provider_type, None),
        "model": (ApiUsage.model, ApiUsage.model, None),
    }
    key_col, label_col, join = dims.get(by, dims["model"])
    q = select(
        key_col,
        label_col,
        func.coalesce(func.sum(ApiUsage.estimated_cost_usd), 0),
        func.coalesce(func.sum(ApiUsage.requests), 0),
        func.coalesce(func.sum(ApiUsage.input_tokens), 0),
        func.coalesce(func.sum(ApiUsage.output_tokens), 0),
        func.coalesce(func.sum(ApiUsage.image_generations), 0),
        func.coalesce(func.avg(ApiUsage.duration_ms), 0),
    ).where(ApiUsage.organization_id == organization_id, ApiUsage.created_at >= since)
    if join is not None:
        q = q.outerjoin(join[0], join[1])
    q = q.group_by(key_col, label_col).order_by(
        func.sum(ApiUsage.estimated_cost_usd).desc(), func.sum(ApiUsage.requests).desc()
    )
    rows = (await session.execute(q)).all()
    fallback = "(no command)" if by == "workflow" else "(unattributed)"
    return [
        {
            "key": str(r[0]) if r[0] is not None else None,
            "label": str(r[1]) if r[1] is not None else fallback,
            "cost_usd": round(float(r[2]), 4),
            "requests": int(r[3]),
            "input_tokens": int(r[4]),
            "output_tokens": int(r[5]),
            "images": int(r[6]),
            "avg_latency_ms": int(r[7]),
        }
        for r in rows
    ]


async def recent_calls(
    session: AsyncSession, organization_id: uuid.UUID, limit: int = 50
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(ApiUsage, Agent.name, WorkflowRun.status)
            .outerjoin(Agent, Agent.id == ApiUsage.agent_id)
            .outerjoin(WorkflowRun, WorkflowRun.id == ApiUsage.run_id)
            .where(ApiUsage.organization_id == organization_id)
            .order_by(ApiUsage.created_at.desc())
            .limit(limit)
        )
    ).all()
    return [
        {
            "id": str(u.id),
            "created_at": u.created_at.isoformat(),
            "agent": name,
            "command": u.command,
            "provider_type": u.provider_type,
            "model": u.model,
            "input_tokens": u.input_tokens,
            "cached_input_tokens": u.cached_input_tokens,
            "output_tokens": u.output_tokens,
            "reasoning_tokens": u.reasoning_tokens,
            "images": u.image_generations,
            "tool_calls": u.tool_calls,
            "cost_usd": float(u.estimated_cost_usd),
            "priced": u.priced,
            "latency_ms": u.duration_ms,
            "status": u.status,
            "error_code": u.error_code,
            "run_id": str(u.run_id) if u.run_id else None,
            "run_status": run_status,
        }
        for u, name, run_status in rows
    ]
