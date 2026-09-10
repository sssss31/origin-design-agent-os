from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AuditLog(UUIDPrimaryKeyMixin, Base):
    """Append-only record of who changed what. Never updated or deleted by the app."""

    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_organization_id_created_at", "organization_id", "created_at"),)

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(
        String(80), nullable=False, comment="e.g. workspace.created, agent.published"
    )
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    before_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SecretRef(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Encrypted credential at rest. The plaintext never leaves `SecretStore.reveal()`."""

    __tablename__ = "secret_refs"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    backend: Mapped[str] = mapped_column(String(20), nullable=False, comment="fernet | env | kms")
    ciphertext: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="fernet token; null for external backends"
    )
    external_ref: Mapped[str | None] = mapped_column(
        String(300), nullable=True, comment="env var or secret-manager path"
    )
    fingerprint: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="safe display hint, never the value"
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
