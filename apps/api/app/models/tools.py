"""Tools (spec §12 tool contract). A tool is versioned; agents bind to tools per agent version."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import AuditedMixin, Base, TimestampMixin, UUIDPrimaryKeyMixin


class Tool(UUIDPrimaryKeyMixin, TimestampMixin, AuditedMixin, Base):
    __tablename__ = "tools"
    __table_args__ = (UniqueConstraint("organization_id", "slug"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    executor_type: Mapped[str] = mapped_column(
        String(30), nullable=False, comment="internal_function | http_api | mcp | sandbox"
    )
    status: Mapped[str] = mapped_column(
        String(20), default="active", nullable=False, comment="active | disabled"
    )
    is_builtin: Mapped[bool] = mapped_column(
        default=False, nullable=False, comment="seeded from app/tools registry"
    )
    active_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("tool_versions.id", ondelete="SET NULL", use_alter=True, name="fk_tools_active_version"),
        nullable=True,
    )

    versions: Mapped[list[ToolVersion]] = relationship(
        back_populates="tool",
        cascade="all, delete-orphan",
        foreign_keys="ToolVersion.tool_id",
        order_by="ToolVersion.version",
    )
    permissions: Mapped[list[ToolPermission]] = relationship(
        back_populates="tool", cascade="all, delete-orphan"
    )


class ToolVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tool_versions"
    __table_args__ = (UniqueConstraint("tool_id", "version"),)

    tool_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tools.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    input_schema: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    output_schema: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    config: Mapped[dict] = mapped_column(
        JSONB, default=dict, nullable=False, comment="endpoint/method/headers, mcp server, sandbox image…"
    )
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    secret_ref_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("secret_refs.id", ondelete="SET NULL"),
        nullable=True,
        comment="credential for http/mcp tools",
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    change_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    tool: Mapped[Tool] = relationship(back_populates="versions", foreign_keys=[tool_id])


class ToolPermission(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Who may trigger runs that use this tool (spec §12 routing step 4)."""

    __tablename__ = "tool_permissions"
    __table_args__ = (UniqueConstraint("tool_id", "subject_type", "subject_key"),)

    tool_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tools.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subject_type: Mapped[str] = mapped_column(String(20), nullable=False, comment="role | workspace")
    subject_key: Mapped[str] = mapped_column(String(64), nullable=False, comment="role name or workspace id")
    allowed: Mapped[bool] = mapped_column(default=True, nullable=False)
    limits_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, nullable=False, comment="e.g. max_calls_per_run"
    )

    tool: Mapped[Tool] = relationship(back_populates="permissions")
