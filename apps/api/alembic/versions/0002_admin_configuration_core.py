"""admin configuration core

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-10 18:03:13.104750+00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("command", sa.String(length=41), nullable=False, comment="slash command, e.g. /resize"),
        sa.Column("description", sa.Text(), nullable=False, comment="routing description"),
        sa.Column("status", sa.String(length=20), nullable=False, comment="draft | active | disabled"),
        sa.Column("is_manager", sa.Boolean(), nullable=False, comment="routes /auto and plain messages"),
        sa.Column("active_version_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_agents_created_by_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_agents_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["users.id"], name=op.f("fk_agents_updated_by_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agents")),
        sa.UniqueConstraint("organization_id", "slug", name=op.f("uq_agents_organization_id_slug")),
    )
    op.create_index(op.f("ix_agents_organization_id"), "agents", ["organization_id"], unique=False)
    op.create_index(
        "uq_agents_active_command",
        "agents",
        ["organization_id", "command"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_table(
        "ai_providers",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("type", sa.String(length=40), nullable=False, comment="openai | echo | (future providers)"),
        sa.Column("base_url", sa.String(length=300), nullable=True),
        sa.Column("secret_ref_id", sa.Uuid(), nullable=True),
        sa.Column("secret_fingerprint", sa.String(length=16), nullable=True, comment="display only"),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="org/project ids etc.",
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("default_model", sa.String(length=120), nullable=True),
        sa.Column("rate_limit_policy", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("health_status", sa.String(length=20), nullable=False, comment="unknown | ok | error"),
        sa.Column("health_message", sa.Text(), nullable=True),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_ai_providers_created_by_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_ai_providers_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["secret_ref_id"],
            ["secret_refs.id"],
            name=op.f("fk_ai_providers_secret_ref_id_secret_refs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["users.id"], name=op.f("fk_ai_providers_updated_by_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_providers")),
        sa.UniqueConstraint("organization_id", "slug", name=op.f("uq_ai_providers_organization_id_slug")),
    )
    op.create_index(
        op.f("ix_ai_providers_organization_id"), "ai_providers", ["organization_id"], unique=False
    )
    op.create_table(
        "tools",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "executor_type",
            sa.String(length=30),
            nullable=False,
            comment="internal_function | http_api | mcp | sandbox",
        ),
        sa.Column("status", sa.String(length=20), nullable=False, comment="active | disabled"),
        sa.Column("is_builtin", sa.Boolean(), nullable=False, comment="seeded from app/tools registry"),
        sa.Column("active_version_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_tools_created_by_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_tools_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["users.id"], name=op.f("fk_tools_updated_by_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tools")),
        sa.UniqueConstraint("organization_id", "slug", name=op.f("uq_tools_organization_id_slug")),
    )
    op.create_index(op.f("ix_tools_organization_id"), "tools", ["organization_id"], unique=False)
    op.create_table(
        "agent_versions",
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_id", sa.Uuid(), nullable=True),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column(
            "handoff_description", sa.Text(), nullable=False, comment="when the Manager should delegate here"
        ),
        sa.Column(
            "model_settings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="temperature, reasoning, …",
        ),
        sa.Column(
            "input_schema",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="requirement contract",
        ),
        sa.Column("output_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("can_ask_clarification", sa.Boolean(), nullable=False),
        sa.Column("max_steps", sa.Integer(), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("change_note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["agent_id"], ["agents.id"], name=op.f("fk_agent_versions_agent_id_agents"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_agent_versions_created_by_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["ai_providers.id"],
            name=op.f("fk_agent_versions_provider_id_ai_providers"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_versions")),
        sa.UniqueConstraint("agent_id", "version", name=op.f("uq_agent_versions_agent_id_version")),
    )
    op.create_index(op.f("ix_agent_versions_agent_id"), "agent_versions", ["agent_id"], unique=False)
    op.create_table(
        "provider_models",
        sa.Column("provider_id", sa.Uuid(), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=True),
        sa.Column(
            "capabilities",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="text/vision/image_generation flags",
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["ai_providers.id"],
            name=op.f("fk_provider_models_provider_id_ai_providers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_provider_models")),
        sa.UniqueConstraint("provider_id", "model", name=op.f("uq_provider_models_provider_id_model")),
    )
    op.create_index(op.f("ix_provider_models_provider_id"), "provider_models", ["provider_id"], unique=False)
    op.create_table(
        "skills",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, comment="draft | active | disabled"),
        sa.Column("scope", sa.String(length=20), nullable=False, comment="global | organization | workspace"),
        sa.Column("workspace_id", sa.Uuid(), nullable=True),
        sa.Column("active_version_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_skills_created_by_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_skills_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["users.id"], name=op.f("fk_skills_updated_by_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_skills_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_skills")),
        sa.UniqueConstraint("organization_id", "slug", name=op.f("uq_skills_organization_id_slug")),
    )
    op.create_index(op.f("ix_skills_organization_id"), "skills", ["organization_id"], unique=False)
    op.create_table(
        "tool_permissions",
        sa.Column("tool_id", sa.Uuid(), nullable=False),
        sa.Column("subject_type", sa.String(length=20), nullable=False, comment="role | workspace"),
        sa.Column("subject_key", sa.String(length=64), nullable=False, comment="role name or workspace id"),
        sa.Column("allowed", sa.Boolean(), nullable=False),
        sa.Column(
            "limits_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="e.g. max_calls_per_run",
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["tool_id"], ["tools.id"], name=op.f("fk_tool_permissions_tool_id_tools"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tool_permissions")),
        sa.UniqueConstraint(
            "tool_id",
            "subject_type",
            "subject_key",
            name=op.f("uq_tool_permissions_tool_id_subject_type_subject_key"),
        ),
    )
    op.create_index(op.f("ix_tool_permissions_tool_id"), "tool_permissions", ["tool_id"], unique=False)
    op.create_table(
        "tool_versions",
        sa.Column("tool_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("input_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("output_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="endpoint/method/headers, mcp server, sandbox image…",
        ),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("secret_ref_id", sa.Uuid(), nullable=True, comment="credential for http/mcp tools"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("change_note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_tool_versions_created_by_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["secret_ref_id"],
            ["secret_refs.id"],
            name=op.f("fk_tool_versions_secret_ref_id_secret_refs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tool_id"], ["tools.id"], name=op.f("fk_tool_versions_tool_id_tools"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tool_versions")),
        sa.UniqueConstraint("tool_id", "version", name=op.f("uq_tool_versions_tool_id_version")),
    )
    op.create_index(op.f("ix_tool_versions_tool_id"), "tool_versions", ["tool_id"], unique=False)
    op.create_table(
        "agent_handoffs",
        sa.Column("agent_version_id", sa.Uuid(), nullable=False),
        sa.Column("target_agent_id", sa.Uuid(), nullable=False),
        sa.Column("routing_hint", sa.Text(), nullable=False, comment="manager routing hint"),
        sa.Column("is_failure_route", sa.Boolean(), nullable=False, comment="route on QC failure"),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["agent_version_id"],
            ["agent_versions.id"],
            name=op.f("fk_agent_handoffs_agent_version_id_agent_versions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_agent_id"],
            ["agents.id"],
            name=op.f("fk_agent_handoffs_target_agent_id_agents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_handoffs")),
        sa.UniqueConstraint(
            "agent_version_id",
            "target_agent_id",
            name=op.f("uq_agent_handoffs_agent_version_id_target_agent_id"),
        ),
    )
    op.create_index(
        op.f("ix_agent_handoffs_agent_version_id"), "agent_handoffs", ["agent_version_id"], unique=False
    )
    op.create_index(
        op.f("ix_agent_handoffs_target_agent_id"), "agent_handoffs", ["target_agent_id"], unique=False
    )
    op.create_table(
        "agent_tool_bindings",
        sa.Column("agent_version_id", sa.Uuid(), nullable=False),
        sa.Column("tool_id", sa.Uuid(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "settings_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="per-tool settings for this agent",
        ),
        sa.Column("max_calls_per_run", sa.Integer(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["agent_version_id"],
            ["agent_versions.id"],
            name=op.f("fk_agent_tool_bindings_agent_version_id_agent_versions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tool_id"], ["tools.id"], name=op.f("fk_agent_tool_bindings_tool_id_tools"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_tool_bindings")),
        sa.UniqueConstraint(
            "agent_version_id", "tool_id", name=op.f("uq_agent_tool_bindings_agent_version_id_tool_id")
        ),
    )
    op.create_index(
        op.f("ix_agent_tool_bindings_agent_version_id"),
        "agent_tool_bindings",
        ["agent_version_id"],
        unique=False,
    )
    op.create_index(op.f("ix_agent_tool_bindings_tool_id"), "agent_tool_bindings", ["tool_id"], unique=False)
    op.create_table(
        "skill_versions",
        sa.Column("skill_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column(
            "variables_schema",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="JSON schema of configurable variables",
        ),
        sa.Column("variables_defaults", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "tool_requirements",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="tool slugs that must be bound",
        ),
        sa.Column("default_priority", sa.Integer(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("change_note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_skill_versions_created_by_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"], ["skills.id"], name=op.f("fk_skill_versions_skill_id_skills"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_skill_versions")),
        sa.UniqueConstraint("skill_id", "version", name=op.f("uq_skill_versions_skill_id_version")),
    )
    op.create_index(op.f("ix_skill_versions_skill_id"), "skill_versions", ["skill_id"], unique=False)
    op.create_table(
        "agent_skill_bindings",
        sa.Column("agent_version_id", sa.Uuid(), nullable=False),
        sa.Column("skill_id", sa.Uuid(), nullable=False),
        sa.Column(
            "skill_version_id", sa.Uuid(), nullable=True, comment="pinned version; null = follow active"
        ),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "variables",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="overrides for the skill's variables",
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["agent_version_id"],
            ["agent_versions.id"],
            name=op.f("fk_agent_skill_bindings_agent_version_id_agent_versions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"],
            ["skills.id"],
            name=op.f("fk_agent_skill_bindings_skill_id_skills"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["skill_version_id"],
            ["skill_versions.id"],
            name=op.f("fk_agent_skill_bindings_skill_version_id_skill_versions"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_skill_bindings")),
        sa.UniqueConstraint(
            "agent_version_id", "skill_id", name=op.f("uq_agent_skill_bindings_agent_version_id_skill_id")
        ),
    )
    op.create_index(
        op.f("ix_agent_skill_bindings_agent_version_id"),
        "agent_skill_bindings",
        ["agent_version_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_skill_bindings_skill_id"), "agent_skill_bindings", ["skill_id"], unique=False
    )
    op.create_table(
        "skill_files",
        sa.Column("skill_version_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_skill_files_created_by_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["skill_version_id"],
            ["skill_versions.id"],
            name=op.f("fk_skill_files_skill_version_id_skill_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_skill_files")),
    )
    op.create_index(
        op.f("ix_skill_files_skill_version_id"), "skill_files", ["skill_version_id"], unique=False
    )

    # Circular references (entity <-> its versions) are added after both tables exist.
    op.create_foreign_key(
        "fk_agents_active_version",
        "agents",
        "agent_versions",
        ["active_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_tools_active_version",
        "tools",
        "tool_versions",
        ["active_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_skills_active_version",
        "skills",
        "skill_versions",
        ["active_version_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_agents_active_version", "agents", type_="foreignkey")
    op.drop_constraint("fk_tools_active_version", "tools", type_="foreignkey")
    op.drop_constraint("fk_skills_active_version", "skills", type_="foreignkey")
    op.drop_index(op.f("ix_skill_files_skill_version_id"), table_name="skill_files")
    op.drop_table("skill_files")
    op.drop_index(op.f("ix_agent_skill_bindings_skill_id"), table_name="agent_skill_bindings")
    op.drop_index(op.f("ix_agent_skill_bindings_agent_version_id"), table_name="agent_skill_bindings")
    op.drop_table("agent_skill_bindings")
    op.drop_index(op.f("ix_skill_versions_skill_id"), table_name="skill_versions")
    op.drop_table("skill_versions")
    op.drop_index(op.f("ix_agent_tool_bindings_tool_id"), table_name="agent_tool_bindings")
    op.drop_index(op.f("ix_agent_tool_bindings_agent_version_id"), table_name="agent_tool_bindings")
    op.drop_table("agent_tool_bindings")
    op.drop_index(op.f("ix_agent_handoffs_target_agent_id"), table_name="agent_handoffs")
    op.drop_index(op.f("ix_agent_handoffs_agent_version_id"), table_name="agent_handoffs")
    op.drop_table("agent_handoffs")
    op.drop_index(op.f("ix_tool_versions_tool_id"), table_name="tool_versions")
    op.drop_table("tool_versions")
    op.drop_index(op.f("ix_tool_permissions_tool_id"), table_name="tool_permissions")
    op.drop_table("tool_permissions")
    op.drop_index(op.f("ix_skills_organization_id"), table_name="skills")
    op.drop_table("skills")
    op.drop_index(op.f("ix_provider_models_provider_id"), table_name="provider_models")
    op.drop_table("provider_models")
    op.drop_index(op.f("ix_agent_versions_agent_id"), table_name="agent_versions")
    op.drop_table("agent_versions")
    op.drop_index(op.f("ix_tools_organization_id"), table_name="tools")
    op.drop_table("tools")
    op.drop_index(op.f("ix_ai_providers_organization_id"), table_name="ai_providers")
    op.drop_table("ai_providers")
    op.drop_index(
        "uq_agents_active_command", table_name="agents", postgresql_where=sa.text("status = 'active'")
    )
    op.drop_index(op.f("ix_agents_organization_id"), table_name="agents")
    op.drop_table("agents")
