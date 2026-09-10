"""Skills (spec §5): reusable, versioned instruction packages attached to agents."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import AuditedMixin, Base, TimestampMixin, UUIDPrimaryKeyMixin


class Skill(UUIDPrimaryKeyMixin, TimestampMixin, AuditedMixin, Base):
    __tablename__ = "skills"
    __table_args__ = (UniqueConstraint("organization_id", "slug"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="draft", nullable=False, comment="draft | active | disabled"
    )
    scope: Mapped[str] = mapped_column(
        String(20), default="organization", nullable=False, comment="global | organization | workspace"
    )
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True
    )
    active_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("skill_versions.id", ondelete="SET NULL", use_alter=True, name="fk_skills_active_version"),
        nullable=True,
    )

    versions: Mapped[list[SkillVersion]] = relationship(
        back_populates="skill",
        cascade="all, delete-orphan",
        foreign_keys="SkillVersion.skill_id",
        order_by="SkillVersion.version",
    )


class SkillVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Immutable once published. At most one unpublished draft per skill."""

    __tablename__ = "skill_versions"
    __table_args__ = (UniqueConstraint("skill_id", "version"),)

    skill_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    instructions: Mapped[str] = mapped_column(Text, default="", nullable=False)
    variables_schema: Mapped[dict] = mapped_column(
        JSONB, default=dict, nullable=False, comment="JSON schema of configurable variables"
    )
    variables_defaults: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    tool_requirements: Mapped[list] = mapped_column(
        JSONB, default=list, nullable=False, comment="tool slugs that must be bound"
    )
    default_priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    change_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    skill: Mapped[Skill] = relationship(back_populates="versions", foreign_keys=[skill_id])
    files: Mapped[list[SkillFile]] = relationship(
        back_populates="skill_version", cascade="all, delete-orphan"
    )


class SkillFile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Knowledge/reference file attached to a skill version; stored via ObjectStorage."""

    __tablename__ = "skill_files"

    skill_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("skill_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    skill_version: Mapped[SkillVersion] = relationship(back_populates="files")
