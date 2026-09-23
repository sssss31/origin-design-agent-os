"""Admin → Usage & Cost (spec §15) and model pricing configuration."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.v1.admin import AdminAuth
from app.core.authz import DB
from app.core.errors import NotFound
from app.models.workflows import ModelPricing
from app.services import audit
from app.services.usage import breakdown, recent_calls, summary

router = APIRouter(prefix="/usage")


class UsageSummaryOut(BaseModel):
    currency: str
    fx_usd_rate: float
    today: dict[str, Any]
    month: dict[str, Any]
    last_30d: dict[str, Any]


class PricingIn(BaseModel):
    provider_type: str = Field(min_length=1, max_length=40)
    model: str = Field(min_length=1, max_length=120, description="exact id, or prefix ending with * (gpt-5*)")
    input_per_million: Decimal = Field(default=Decimal(0), ge=0)
    cached_input_per_million: Decimal = Field(default=Decimal(0), ge=0)
    output_per_million: Decimal = Field(default=Decimal(0), ge=0)
    image_per_unit: Decimal = Field(default=Decimal(0), ge=0)
    note: str | None = Field(default=None, max_length=500)


class PricingOut(BaseModel):
    id: uuid.UUID
    provider_type: str
    model: str
    input_per_million: float
    cached_input_per_million: float
    output_per_million: float
    image_per_unit: float
    currency: str
    note: str | None
    updated_at: datetime


def _out(p: ModelPricing) -> PricingOut:
    return PricingOut(
        id=p.id,
        provider_type=p.provider_type,
        model=p.model,
        input_per_million=float(p.input_per_million),
        cached_input_per_million=float(p.cached_input_per_million),
        output_per_million=float(p.output_per_million),
        image_per_unit=float(p.image_per_unit),
        currency=p.currency,
        note=p.note,
        updated_at=p.updated_at,
    )


@router.get("/summary", response_model=UsageSummaryOut)
async def usage_summary(ctx: AdminAuth, session: DB) -> UsageSummaryOut:
    return UsageSummaryOut(**await summary(session, ctx.require_organization()))


@router.get("/breakdown")
async def usage_breakdown(
    ctx: AdminAuth,
    session: DB,
    by: Literal["agent", "model", "user", "workspace", "workflow", "provider"] = "agent",
    range: Literal["today", "month", "7d", "30d"] = "month",  # noqa: A002
) -> list[dict[str, Any]]:
    return await breakdown(session, ctx.require_organization(), by, range)


@router.get("/calls")
async def usage_calls(
    ctx: AdminAuth, session: DB, limit: int = Query(default=50, ge=1, le=500)
) -> list[dict[str, Any]]:
    return await recent_calls(session, ctx.require_organization(), limit)


@router.get("/pricing", response_model=list[PricingOut])
async def list_pricing(ctx: AdminAuth, session: DB) -> list[PricingOut]:
    rows = await session.scalars(
        select(ModelPricing)
        .where(ModelPricing.organization_id == ctx.require_organization())
        .order_by(ModelPricing.provider_type, ModelPricing.model)
    )
    return [_out(p) for p in rows.all()]


@router.put("/pricing", response_model=PricingOut)
async def upsert_pricing(body: PricingIn, ctx: AdminAuth, session: DB) -> PricingOut:
    org = ctx.require_organization()
    row = await session.scalar(
        select(ModelPricing).where(
            ModelPricing.organization_id == org,
            ModelPricing.provider_type == body.provider_type,
            ModelPricing.model == body.model,
        )
    )
    before = _out(row).model_dump(mode="json") if row else None
    if row is None:
        row = ModelPricing(organization_id=org, provider_type=body.provider_type, model=body.model)
        session.add(row)
    row.input_per_million = body.input_per_million
    row.cached_input_per_million = body.cached_input_per_million
    row.output_per_million = body.output_per_million
    row.image_per_unit = body.image_per_unit
    row.note = body.note
    row.updated_by = ctx.user_id
    await session.flush()
    await audit.record(
        session,
        action="pricing.updated",
        entity_type="model_pricing",
        entity_id=row.id,
        organization_id=org,
        actor_user_id=ctx.user_id,
        before=before,
        after=_out(row).model_dump(mode="json"),
        request_id=ctx.request_id,
    )
    return _out(row)


@router.delete("/pricing/{pricing_id}", status_code=204)
async def delete_pricing(pricing_id: uuid.UUID, ctx: AdminAuth, session: DB) -> None:
    org = ctx.require_organization()
    row = await session.scalar(
        select(ModelPricing).where(ModelPricing.id == pricing_id, ModelPricing.organization_id == org)
    )
    if row is None:
        raise NotFound("Pricing row not found", code="pricing_not_found")
    before = _out(row).model_dump(mode="json")
    await session.delete(row)
    await session.flush()
    await audit.record(
        session,
        action="pricing.deleted",
        entity_type="model_pricing",
        entity_id=pricing_id,
        organization_id=org,
        actor_user_id=ctx.user_id,
        before=before,
        request_id=ctx.request_id,
    )
