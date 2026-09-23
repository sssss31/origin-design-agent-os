"""AI providers and their model allowlists (spec §6). Secrets live in `secret_refs`."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import AuditedMixin, Base, TimestampMixin, UUIDPrimaryKeyMixin


class AIProvider(UUIDPrimaryKeyMixin, TimestampMixin, AuditedMixin, Base):
    __tablename__ = "ai_providers"
    __table_args__ = (UniqueConstraint("organization_id", "slug"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    type: Mapped[str] = mapped_column(
        String(40), nullable=False, comment="openai | echo | (future providers)"
    )
    base_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    secret_ref_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("secret_refs.id", ondelete="SET NULL"), nullable=True
    )
    secret_fingerprint: Mapped[str | None] = mapped_column(String(16), nullable=True, comment="display only")
    key_preview: Mapped[str | None] = mapped_column(
        String(48), nullable=True, comment="masked form e.g. sk-proj-••••••••7Xk2; never the value"
    )
    environment: Mapped[str] = mapped_column(
        String(20), default="production", nullable=False, comment="production | staging | development"
    )
    metadata_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, nullable=False, comment="org/project ids etc."
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    default_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    rate_limit_policy: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    health_status: Mapped[str] = mapped_column(
        String(20), default="unknown", nullable=False, comment="unknown | ok | error"
    )
    health_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    models: Mapped[list[ProviderModel]] = relationship(
        back_populates="provider", cascade="all, delete-orphan", order_by="ProviderModel.model"
    )


class ProviderModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Model allowlist entry. Agents may only select enabled rows of their provider."""

    __tablename__ = "provider_models"
    __table_args__ = (UniqueConstraint("provider_id", "model"),)

    provider_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("ai_providers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    capabilities: Mapped[dict] = mapped_column(
        JSONB, default=dict, nullable=False, comment="text/vision/image_generation flags"
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    provider: Mapped[AIProvider] = relationship(back_populates="models")
