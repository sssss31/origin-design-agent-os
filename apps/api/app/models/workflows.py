"""Workflow definitions, runs, node runs and the execution event log (spec §9, §10).

`execution_events` is the source of truth for a run's timeline; `workflow_runs.status` and
`node_runs.status` are projections kept in sync in the same transaction.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import AuditedMixin, Base, TimestampMixin, UUIDPrimaryKeyMixin


class WorkflowDefinition(UUIDPrimaryKeyMixin, TimestampMixin, AuditedMixin, Base):
    __tablename__ = "workflow_definitions"
    __table_args__ = (UniqueConstraint("organization_id", "slug"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    trigger_type: Mapped[str] = mapped_column(
        String(20), default="command", nullable=False, comment="command | manager | manual"
    )
    trigger_command: Mapped[str | None] = mapped_column(String(41), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    active_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey(
            "workflow_versions.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_workflow_definitions_active_version",
        ),
        nullable=True,
    )

    versions: Mapped[list[WorkflowVersion]] = relationship(
        back_populates="workflow",
        cascade="all, delete-orphan",
        foreign_keys="WorkflowVersion.workflow_id",
        order_by="WorkflowVersion.version",
    )


class WorkflowVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "workflow_versions"
    __table_args__ = (UniqueConstraint("workflow_id", "version"),)

    workflow_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("workflow_definitions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    nodes_json: Mapped[list] = mapped_column(
        JSONB, default=list, nullable=False, comment="ordered NodeSpec list (V0 sequential)"
    )
    edges_json: Mapped[list] = mapped_column(
        JSONB, default=list, nullable=False, comment="EdgeSpec list for the DAG scheduler"
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    workflow: Mapped[WorkflowDefinition] = relationship(back_populates="versions", foreign_keys=[workflow_id])


class WorkflowRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "workflow_runs"
    __table_args__ = (
        Index("ix_workflow_runs_project_id_created_at", "project_id", "created_at"),
        Index("ix_workflow_runs_status", "status"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    workflow_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("workflow_versions.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default="QUEUED", nullable=False)
    command: Mapped[str | None] = mapped_column(String(41), nullable=True)
    user_input: Mapped[str] = mapped_column(Text, default="", nullable=False)
    entry_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    plan_json: Mapped[list] = mapped_column(
        JSONB, default=list, nullable=False, comment="node specs snapshot; grows when the Manager delegates"
    )
    input_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, nullable=False, comment="selected assets/artifacts, options"
    )
    result_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, nullable=False, comment="safe summary of the outcome"
    )
    error_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="worker liveness for stale-run recovery"
    )

    nodes: Mapped[list[NodeRun]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="NodeRun.index"
    )


class NodeRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "node_runs"
    __table_args__ = (UniqueConstraint("run_id", "node_id"),)

    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    node_id: Mapped[str] = mapped_column(String(80), nullable=False)
    index: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    kind: Mapped[str] = mapped_column(
        String(30), nullable=False, comment="parse | context | agent | manager | save"
    )
    status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    agent_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("agent_versions.id", ondelete="SET NULL"), nullable=True
    )
    input_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    output_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, nullable=False, comment="safe output summary + structured output"
    )
    error_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    resume_state_json: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="opaque runner state while WAITING_FOR_USER"
    )
    question: Mapped[str | None] = mapped_column(Text, nullable=True)
    question_schema: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    run: Mapped[WorkflowRun] = relationship(back_populates="nodes")


class ExecutionEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "execution_events"
    __table_args__ = (UniqueConstraint("run_id", "sequence_no"),)

    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    node_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("node_runs.id", ondelete="SET NULL"), nullable=True
    )
    payload_json: Mapped[dict] = mapped_column(
        JSONB, default=dict, nullable=False, comment="SafeEventPayload only"
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ApiUsage(UUIDPrimaryKeyMixin, Base):
    """Provider usage per run/node for quotas and cost analytics (spec §10 governance)."""

    __tablename__ = "api_usage"
    __table_args__ = (Index("ix_api_usage_organization_id_created_at", "organization_id", "created_at"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("workflow_runs.id", ondelete="SET NULL"), nullable=True
    )
    node_run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    provider_type: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("ai_providers.id", ondelete="SET NULL"), nullable=True
    )
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    agent_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="SET NULL"), nullable=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    command: Mapped[str | None] = mapped_column(String(41), nullable=True)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cached_input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reasoning_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tool_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    image_generations: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    requests: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    estimated_cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=0, nullable=False)
    priced: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="a price row matched"
    )
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="ok", nullable=False, comment="ok | error | clarification | test"
    )
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ModelPricing(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Admin-configurable prices (USD per million tokens / per image). Never hardcoded."""

    __tablename__ = "model_pricing"
    __table_args__ = (UniqueConstraint("organization_id", "provider_type", "model"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider_type: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(
        String(120), nullable=False, comment="exact model id or prefix ending with *"
    )
    input_per_million: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=0, nullable=False)
    cached_input_per_million: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=0, nullable=False)
    output_per_million: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=0, nullable=False)
    image_per_unit: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class ErrorEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "error_events"
    __table_args__ = (Index("ix_error_events_organization_id_created_at", "organization_id", "created_at"),)

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    node_run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    retryable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
