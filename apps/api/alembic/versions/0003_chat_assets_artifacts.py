"""chat assets artifacts

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-11 05:34:51.515442+00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assets",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, comment="pending | ready | failed"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("current_version_id", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_assets_created_by_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_assets_project_id_projects"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assets")),
    )
    op.create_index("ix_assets_project_id_created_at", "assets", ["project_id", "created_at"], unique=False)
    op.create_table(
        "conversations",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, comment="active | archived"),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_conversations_created_by_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_conversations_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversations")),
    )
    op.create_index(
        "ix_conversations_project_id_last_message_at",
        "conversations",
        ["project_id", "last_message_at"],
        unique=False,
    )
    op.create_table(
        "artifacts",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("parent_artifact_id", sa.Uuid(), nullable=True),
        sa.Column("current_version_id", sa.Uuid(), nullable=True),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["approved_by"], ["users.id"], name=op.f("fk_artifacts_approved_by_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_artifacts_conversation_id_conversations"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_artifacts_created_by_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["parent_artifact_id"],
            ["artifacts.id"],
            name=op.f("fk_artifacts_parent_artifact_id_artifacts"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_artifacts_project_id_projects"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_artifacts_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_artifacts")),
    )
    op.create_index(
        op.f("ix_artifacts_parent_artifact_id"), "artifacts", ["parent_artifact_id"], unique=False
    )
    op.create_index(
        "ix_artifacts_project_id_created_at", "artifacts", ["project_id", "created_at"], unique=False
    )
    op.create_index(op.f("ix_artifacts_workspace_id"), "artifacts", ["workspace_id"], unique=False)
    op.create_table(
        "asset_versions",
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["asset_id"], ["assets.id"], name=op.f("fk_asset_versions_asset_id_assets"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_asset_versions_created_by_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_asset_versions")),
        sa.UniqueConstraint("asset_id", "version", name=op.f("uq_asset_versions_asset_id_version")),
    )
    op.create_index(op.f("ix_asset_versions_asset_id"), "asset_versions", ["asset_id"], unique=False)
    op.create_table(
        "messages",
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False, comment="user | assistant | system"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "command", sa.String(length=41), nullable=True, comment="explicit slash command, kept visible"
        ),
        sa.Column("agent_id", sa.Uuid(), nullable=True),
        sa.Column("agent_version_id", sa.Uuid(), nullable=True),
        sa.Column(
            "run_id",
            sa.Uuid(),
            nullable=True,
            comment="workflow run that produced/was triggered by this message",
        ),
        sa.Column("author_user_id", sa.Uuid(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["agent_id"], ["agents.id"], name=op.f("fk_messages_agent_id_agents"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["agent_version_id"],
            ["agent_versions.id"],
            name=op.f("fk_messages_agent_version_id_agent_versions"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["author_user_id"],
            ["users.id"],
            name=op.f("fk_messages_author_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_messages_conversation_id_conversations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_messages")),
    )
    op.create_index(
        "ix_messages_conversation_id_created_at", "messages", ["conversation_id", "created_at"], unique=False
    )
    op.create_table(
        "artifact_versions",
        sa.Column("artifact_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("node_run_id", sa.Uuid(), nullable=True),
        sa.Column("produced_by_agent_version_id", sa.Uuid(), nullable=True),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("dpi", sa.Integer(), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="qc report, export params, source asset ids…",
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["artifact_id"],
            ["artifacts.id"],
            name=op.f("fk_artifact_versions_artifact_id_artifacts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_artifact_versions_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["produced_by_agent_version_id"],
            ["agent_versions.id"],
            name=op.f("fk_artifact_versions_produced_by_agent_version_id_agent_versions"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_artifact_versions")),
        sa.UniqueConstraint(
            "artifact_id", "version_number", name=op.f("uq_artifact_versions_artifact_id_version_number")
        ),
    )
    op.create_index(
        op.f("ix_artifact_versions_artifact_id"), "artifact_versions", ["artifact_id"], unique=False
    )
    op.create_index(op.f("ix_artifact_versions_run_id"), "artifact_versions", ["run_id"], unique=False)
    op.create_table(
        "message_attachments",
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=True),
        sa.Column("artifact_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["artifact_id"],
            ["artifacts.id"],
            name=op.f("fk_message_attachments_artifact_id_artifacts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            name=op.f("fk_message_attachments_asset_id_assets"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            name=op.f("fk_message_attachments_message_id_messages"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_message_attachments")),
    )
    op.create_index(
        op.f("ix_message_attachments_message_id"), "message_attachments", ["message_id"], unique=False
    )

    # Circular references are added after both tables exist.
    op.create_foreign_key(
        "fk_assets_current_version",
        "assets",
        "asset_versions",
        ["current_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_artifacts_current_version",
        "artifacts",
        "artifact_versions",
        ["current_version_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_assets_current_version", "assets", type_="foreignkey")
    op.drop_constraint("fk_artifacts_current_version", "artifacts", type_="foreignkey")
    op.drop_index(op.f("ix_message_attachments_message_id"), table_name="message_attachments")
    op.drop_table("message_attachments")
    op.drop_index(op.f("ix_artifact_versions_run_id"), table_name="artifact_versions")
    op.drop_index(op.f("ix_artifact_versions_artifact_id"), table_name="artifact_versions")
    op.drop_table("artifact_versions")
    op.drop_index("ix_messages_conversation_id_created_at", table_name="messages")
    op.drop_table("messages")
    op.drop_index(op.f("ix_asset_versions_asset_id"), table_name="asset_versions")
    op.drop_table("asset_versions")
    op.drop_index(op.f("ix_artifacts_workspace_id"), table_name="artifacts")
    op.drop_index("ix_artifacts_project_id_created_at", table_name="artifacts")
    op.drop_index(op.f("ix_artifacts_parent_artifact_id"), table_name="artifacts")
    op.drop_table("artifacts")
    op.drop_index("ix_conversations_project_id_last_message_at", table_name="conversations")
    op.drop_table("conversations")
    op.drop_index("ix_assets_project_id_created_at", table_name="assets")
    op.drop_table("assets")
