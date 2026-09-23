"""Custom REST API integrations (spec §7–§10) and their secret references."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import AuditedMixin, Base, TimestampMixin, UUIDPrimaryKeyMixin


class CustomIntegration(UUIDPrimaryKeyMixin, TimestampMixin, AuditedMixin, Base):
    __tablename__ = "custom_integrations"
    __table_args__ = (UniqueConstraint("organization_id", "slug"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    method: Mapped[str] = mapped_column(String(10), default="POST", nullable=False)
    endpoint: Mapped[str] = mapped_column(
        String(2000), nullable=False, comment="https URL; may contain {{variables}}"
    )
    headers_template: Mapped[dict] = mapped_column(
        JSONB, default=dict, nullable=False, comment="header → value template; secrets as {{secrets.name}}"
    )
    query_template: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    body_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_type: Mapped[str] = mapped_column(String(120), default="application/json", nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    max_response_bytes: Mapped[int] = mapped_column(Integer, default=5 * 1024 * 1024, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="active", nullable=False, comment="active | disabled"
    )
    auth_summary: Mapped[str] = mapped_column(
        String(40), default="none", nullable=False, comment="none | header | query | basic | body"
    )
    tool_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("tools.id", ondelete="SET NULL"), nullable=True, comment="the tool agents bind to"
    )
    health_status: Mapped[str] = mapped_column(String(20), default="unknown", nullable=False)
    health_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    request_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    secrets: Mapped[list[IntegrationSecret]] = relationship(
        back_populates="integration", cascade="all, delete-orphan", order_by="IntegrationSecret.name"
    )


class IntegrationSecret(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """`{{secrets.<name>}}` → encrypted secret reference. Values never live in templates."""

    __tablename__ = "integration_secrets"
    __table_args__ = (UniqueConstraint("integration_id", "name"),)

    integration_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("custom_integrations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    secret_ref_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("secret_refs.id", ondelete="CASCADE"), nullable=False
    )
    fingerprint: Mapped[str] = mapped_column(String(16), nullable=False)
    key_preview: Mapped[str | None] = mapped_column(String(48), nullable=True)
    location: Mapped[str] = mapped_column(String(20), default="header", nullable=False)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    integration: Mapped[CustomIntegration] = relationship(back_populates="secrets")
