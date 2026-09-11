"""Assets (inputs) and Artifacts (outputs), both versioned (spec §8)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

ASSET_KINDS = ("logo", "image", "pdf", "brand_guide", "svg", "font", "reference", "other")
ARTIFACT_TYPES = ("image", "svg", "pdf", "json", "qc_report", "source_bundle", "text")
ARTIFACT_STATUSES = ("draft", "generated", "qc_failed", "approved", "final", "archived")


class Asset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "assets"
    __table_args__ = (Index("ix_assets_project_id_created_at", "project_id", "created_at"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), default="other", nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False, comment="pending | ready | failed"
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey(
            "asset_versions.id", ondelete="SET NULL", use_alter=True, name="fk_assets_current_version"
        ),
        nullable=True,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    versions: Mapped[list[AssetVersion]] = relationship(
        back_populates="asset",
        cascade="all, delete-orphan",
        foreign_keys="AssetVersion.asset_id",
        order_by="AssetVersion.version",
    )


class AssetVersion(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "asset_versions"
    __table_args__ = (UniqueConstraint("asset_id", "version"),)

    asset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    asset: Mapped[Asset] = relationship(back_populates="versions", foreign_keys=[asset_id])


class Artifact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "artifacts"
    __table_args__ = (Index("ix_artifacts_project_id_created_at", "project_id", "created_at"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="generated", nullable=False)
    parent_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("artifacts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey(
            "artifact_versions.id", ondelete="SET NULL", use_alter=True, name="fk_artifacts_current_version"
        ),
        nullable=True,
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    versions: Mapped[list[ArtifactVersion]] = relationship(
        back_populates="artifact",
        cascade="all, delete-orphan",
        foreign_keys="ArtifactVersion.artifact_id",
        order_by="ArtifactVersion.version_number",
    )


class ArtifactVersion(UUIDPrimaryKeyMixin, Base):
    """Every generated file. Lineage: run, node, producing agent version, parent artifact."""

    __tablename__ = "artifact_versions"
    __table_args__ = (UniqueConstraint("artifact_id", "version_number"),)

    artifact_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("artifacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    node_run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    produced_by_agent_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("agent_versions.id", ondelete="SET NULL"), nullable=True
    )
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dpi: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, nullable=False, comment="qc report, export params, source asset ids…"
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    artifact: Mapped[Artifact] = relationship(back_populates="versions", foreign_keys=[artifact_id])
