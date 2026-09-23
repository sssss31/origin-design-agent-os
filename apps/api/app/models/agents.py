"""Agents (spec §4) with immutable published versions, bindings and handoffs.

Bindings (skills, tools, handoffs) belong to an *agent version* so a historical run can be
reproduced exactly. Admin endpoints operate on the agent's current draft; publishing makes
the draft the active version atomically.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import AuditedMixin, Base, TimestampMixin, UUIDPrimaryKeyMixin


class Agent(UUIDPrimaryKeyMixin, TimestampMixin, AuditedMixin, Base):
    __tablename__ = "agents"
    __table_args__ = (
        UniqueConstraint("organization_id", "slug"),
        # spec §10: agents(command) UNIQUE WHERE active
        Index(
            "uq_agents_active_command",
            "organization_id",
            "command",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    command: Mapped[str] = mapped_column(String(41), nullable=False, comment="slash command, e.g. /resize")
    description: Mapped[str] = mapped_column(Text, default="", nullable=False, comment="routing description")
    status: Mapped[str] = mapped_column(
        String(20), default="draft", nullable=False, comment="draft | active | disabled"
    )
    # --- connection to an *existing* agent (Origin Agent Workspace V0 §3) --------------------
    connection_type: Mapped[str] = mapped_column(
        String(30),
        default="origin",
        nullable=False,
        comment="origin (prompt built here) | openai_responses | http (existing agent API)",
    )
    api_endpoint: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    api_key_secret_ref_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("secret_refs.id", ondelete="SET NULL"), nullable=True
    )
    api_key_preview: Mapped[str | None] = mapped_column(
        String(48), nullable=True, comment="masked, never the key"
    )
    connection_config: Mapped[dict] = mapped_column(
        JSONB, default=dict, nullable=False, comment="model / prompt_id / request+response mapping"
    )
    connection_status: Mapped[str] = mapped_column(String(20), default="unknown", nullable=False)
    connection_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    connection_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_manager: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="routes /auto and plain messages"
    )
    active_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("agent_versions.id", ondelete="SET NULL", use_alter=True, name="fk_agents_active_version"),
        nullable=True,
    )

    versions: Mapped[list[AgentVersion]] = relationship(
        back_populates="agent",
        cascade="all, delete-orphan",
        foreign_keys="AgentVersion.agent_id",
        order_by="AgentVersion.version",
    )


class AgentVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "agent_versions"
    __table_args__ = (UniqueConstraint("agent_id", "version"),)

    agent_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("ai_providers.id", ondelete="SET NULL"), nullable=True
    )
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    instructions: Mapped[str] = mapped_column(Text, default="", nullable=False)
    handoff_description: Mapped[str] = mapped_column(
        Text, default="", nullable=False, comment="when the Manager should delegate here"
    )
    model_settings: Mapped[dict] = mapped_column(
        JSONB, default=dict, nullable=False, comment="temperature, reasoning, …"
    )
    input_schema: Mapped[dict] = mapped_column(
        JSONB, default=dict, nullable=False, comment="requirement contract"
    )
    output_schema: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    can_ask_clarification: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    max_steps: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    change_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    agent: Mapped[Agent] = relationship(back_populates="versions", foreign_keys=[agent_id])
    skill_bindings: Mapped[list[AgentSkillBinding]] = relationship(
        back_populates="agent_version", cascade="all, delete-orphan", order_by="AgentSkillBinding.priority"
    )
    tool_bindings: Mapped[list[AgentToolBinding]] = relationship(
        back_populates="agent_version", cascade="all, delete-orphan"
    )
    handoffs: Mapped[list[AgentHandoff]] = relationship(
        back_populates="agent_version", cascade="all, delete-orphan"
    )


class AgentSkillBinding(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "agent_skill_bindings"
    __table_args__ = (UniqueConstraint("agent_version_id", "skill_id"),)

    agent_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("agent_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True
    )
    skill_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("skill_versions.id", ondelete="SET NULL"),
        nullable=True,
        comment="pinned version; null = follow active",
    )
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    variables: Mapped[dict] = mapped_column(
        JSONB, default=dict, nullable=False, comment="overrides for the skill's variables"
    )

    agent_version: Mapped[AgentVersion] = relationship(back_populates="skill_bindings")


class AgentToolBinding(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The permission for an agent version to call a tool. No binding, no call."""

    __tablename__ = "agent_tool_bindings"
    __table_args__ = (UniqueConstraint("agent_version_id", "tool_id"),)

    agent_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("agent_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tool_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tools.id", ondelete="CASCADE"), nullable=False, index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    settings_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, nullable=False, comment="per-tool settings for this agent"
    )
    max_calls_per_run: Mapped[int | None] = mapped_column(Integer, nullable=True)

    agent_version: Mapped[AgentVersion] = relationship(back_populates="tool_bindings")


class AgentHandoff(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "agent_handoffs"
    __table_args__ = (UniqueConstraint("agent_version_id", "target_agent_id"),)

    agent_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("agent_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_agent_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    routing_hint: Mapped[str] = mapped_column(
        Text, default="", nullable=False, comment="manager routing hint"
    )
    is_failure_route: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="route on QC failure"
    )

    agent_version: Mapped[AgentVersion] = relationship(back_populates="handoffs")
