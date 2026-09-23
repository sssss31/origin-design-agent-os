"""custom integrations

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-23 07:45:03.294832+00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "custom_integrations",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("method", sa.String(length=10), nullable=False),
        sa.Column(
            "endpoint", sa.String(length=2000), nullable=False, comment="https URL; may contain {{variables}}"
        ),
        sa.Column(
            "headers_template",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="header → value template; secrets as {{secrets.name}}",
        ),
        sa.Column("query_template", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("body_template", sa.Text(), nullable=True),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("max_response_bytes", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, comment="active | disabled"),
        sa.Column(
            "auth_summary",
            sa.String(length=40),
            nullable=False,
            comment="none | header | query | basic | body",
        ),
        sa.Column("tool_id", sa.Uuid(), nullable=True, comment="the tool agents bind to"),
        sa.Column("health_status", sa.String(length=20), nullable=False),
        sa.Column("health_message", sa.Text(), nullable=True),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("total_latency_ms", sa.Integer(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_custom_integrations_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_custom_integrations_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tool_id"], ["tools.id"], name=op.f("fk_custom_integrations_tool_id_tools"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name=op.f("fk_custom_integrations_updated_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_custom_integrations")),
        sa.UniqueConstraint(
            "organization_id", "slug", name=op.f("uq_custom_integrations_organization_id_slug")
        ),
    )
    op.create_index(
        op.f("ix_custom_integrations_organization_id"),
        "custom_integrations",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "integration_secrets",
        sa.Column("integration_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("secret_ref_id", sa.Uuid(), nullable=False),
        sa.Column("fingerprint", sa.String(length=16), nullable=False),
        sa.Column("key_preview", sa.String(length=48), nullable=True),
        sa.Column("location", sa.String(length=20), nullable=False),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["integration_id"],
            ["custom_integrations.id"],
            name=op.f("fk_integration_secrets_integration_id_custom_integrations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["secret_ref_id"],
            ["secret_refs.id"],
            name=op.f("fk_integration_secrets_secret_ref_id_secret_refs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_integration_secrets")),
        sa.UniqueConstraint(
            "integration_id", "name", name=op.f("uq_integration_secrets_integration_id_name")
        ),
    )
    op.create_index(
        op.f("ix_integration_secrets_integration_id"), "integration_secrets", ["integration_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_integration_secrets_integration_id"), table_name="integration_secrets")
    op.drop_table("integration_secrets")
    op.drop_index(op.f("ix_custom_integrations_organization_id"), table_name="custom_integrations")
    op.drop_table("custom_integrations")
