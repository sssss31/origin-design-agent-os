"""workflow runs events usage

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-11 05:45:47.272893+00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "error_events",
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("node_run_id", sa.Uuid(), nullable=True),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("retryable", sa.Boolean(), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_error_events_organization_id_organizations"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_error_events")),
    )
    op.create_index(
        "ix_error_events_organization_id_created_at",
        "error_events",
        ["organization_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "workflow_definitions",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("trigger_type", sa.String(length=20), nullable=False, comment="command | manager | manual"),
        sa.Column("trigger_command", sa.String(length=41), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("active_version_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_workflow_definitions_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_workflow_definitions_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name=op.f("fk_workflow_definitions_updated_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workflow_definitions")),
        sa.UniqueConstraint(
            "organization_id", "slug", name=op.f("uq_workflow_definitions_organization_id_slug")
        ),
    )
    op.create_index(
        op.f("ix_workflow_definitions_organization_id"),
        "workflow_definitions",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "workflow_versions",
        sa.Column("workflow_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "nodes_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="ordered NodeSpec list (V0 sequential)",
        ),
        sa.Column(
            "edges_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="EdgeSpec list for the DAG scheduler",
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_workflow_versions_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workflow_id"],
            ["workflow_definitions.id"],
            name=op.f("fk_workflow_versions_workflow_id_workflow_definitions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workflow_versions")),
        sa.UniqueConstraint("workflow_id", "version", name=op.f("uq_workflow_versions_workflow_id_version")),
    )
    op.create_index(
        op.f("ix_workflow_versions_workflow_id"), "workflow_versions", ["workflow_id"], unique=False
    )
    op.create_table(
        "workflow_runs",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column("workflow_version_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("command", sa.String(length=41), nullable=True),
        sa.Column("user_input", sa.Text(), nullable=False),
        sa.Column("entry_agent_id", sa.Uuid(), nullable=True),
        sa.Column(
            "plan_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="node specs snapshot; grows when the Manager delegates",
        ),
        sa.Column(
            "input_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="selected assets/artifacts, options",
        ),
        sa.Column(
            "result_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="safe summary of the outcome",
        ),
        sa.Column("error_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "heartbeat_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="worker liveness for stale-run recovery",
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_workflow_runs_conversation_id_conversations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_workflow_runs_created_by_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["entry_agent_id"],
            ["agents.id"],
            name=op.f("fk_workflow_runs_entry_agent_id_agents"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            name=op.f("fk_workflow_runs_message_id_messages"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_workflow_runs_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_workflow_runs_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workflow_version_id"],
            ["workflow_versions.id"],
            name=op.f("fk_workflow_runs_workflow_version_id_workflow_versions"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_workflow_runs_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workflow_runs")),
    )
    op.create_index(
        op.f("ix_workflow_runs_conversation_id"), "workflow_runs", ["conversation_id"], unique=False
    )
    op.create_index(
        op.f("ix_workflow_runs_organization_id"), "workflow_runs", ["organization_id"], unique=False
    )
    op.create_index(
        "ix_workflow_runs_project_id_created_at", "workflow_runs", ["project_id", "created_at"], unique=False
    )
    op.create_index("ix_workflow_runs_status", "workflow_runs", ["status"], unique=False)
    op.create_table(
        "api_usage",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("node_run_id", sa.Uuid(), nullable=True),
        sa.Column("provider_type", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("tool_calls", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_api_usage_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["workflow_runs.id"],
            name=op.f("fk_api_usage_run_id_workflow_runs"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_api_usage")),
    )
    op.create_index(
        "ix_api_usage_organization_id_created_at",
        "api_usage",
        ["organization_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "node_runs",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("node_id", sa.String(length=80), nullable=False),
        sa.Column("index", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column(
            "kind", sa.String(length=30), nullable=False, comment="parse | context | agent | manager | save"
        ),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=True),
        sa.Column("agent_version_id", sa.Uuid(), nullable=True),
        sa.Column("input_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "output_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="safe output summary + structured output",
        ),
        sa.Column("error_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "resume_state_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="opaque runner state while WAITING_FOR_USER",
        ),
        sa.Column("question", sa.Text(), nullable=True),
        sa.Column("question_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["agent_id"], ["agents.id"], name=op.f("fk_node_runs_agent_id_agents"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["agent_version_id"],
            ["agent_versions.id"],
            name=op.f("fk_node_runs_agent_version_id_agent_versions"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["workflow_runs.id"],
            name=op.f("fk_node_runs_run_id_workflow_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_node_runs")),
        sa.UniqueConstraint("run_id", "node_id", name=op.f("uq_node_runs_run_id_node_id")),
    )
    op.create_index(op.f("ix_node_runs_run_id"), "node_runs", ["run_id"], unique=False)
    op.create_table(
        "execution_events",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=40), nullable=False),
        sa.Column("node_run_id", sa.Uuid(), nullable=True),
        sa.Column(
            "payload_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="SafeEventPayload only",
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["node_run_id"],
            ["node_runs.id"],
            name=op.f("fk_execution_events_node_run_id_node_runs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["workflow_runs.id"],
            name=op.f("fk_execution_events_run_id_workflow_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_execution_events")),
        sa.UniqueConstraint("run_id", "sequence_no", name=op.f("uq_execution_events_run_id_sequence_no")),
    )
    op.create_index(op.f("ix_execution_events_run_id"), "execution_events", ["run_id"], unique=False)

    # Circular references are added after both tables exist.
    op.create_foreign_key(
        "fk_workflow_definitions_active_version",
        "workflow_definitions",
        "workflow_versions",
        ["active_version_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_workflow_definitions_active_version", "workflow_definitions", type_="foreignkey")
    op.drop_index(op.f("ix_execution_events_run_id"), table_name="execution_events")
    op.drop_table("execution_events")
    op.drop_index(op.f("ix_node_runs_run_id"), table_name="node_runs")
    op.drop_table("node_runs")
    op.drop_index("ix_api_usage_organization_id_created_at", table_name="api_usage")
    op.drop_table("api_usage")
    op.drop_index("ix_workflow_runs_status", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_project_id_created_at", table_name="workflow_runs")
    op.drop_index(op.f("ix_workflow_runs_organization_id"), table_name="workflow_runs")
    op.drop_index(op.f("ix_workflow_runs_conversation_id"), table_name="workflow_runs")
    op.drop_table("workflow_runs")
    op.drop_index(op.f("ix_workflow_versions_workflow_id"), table_name="workflow_versions")
    op.drop_table("workflow_versions")
    op.drop_index(op.f("ix_workflow_definitions_organization_id"), table_name="workflow_definitions")
    op.drop_table("workflow_definitions")
    op.drop_index("ix_error_events_organization_id_created_at", table_name="error_events")
    op.drop_table("error_events")
