"""usage cost and model pricing

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-23 08:07:13.293602+00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_pricing",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("provider_type", sa.String(length=40), nullable=False),
        sa.Column(
            "model", sa.String(length=120), nullable=False, comment="exact model id or prefix ending with *"
        ),
        sa.Column("input_per_million", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column("cached_input_per_million", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column("output_per_million", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column("image_per_unit", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_model_pricing_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["users.id"], name=op.f("fk_model_pricing_updated_by_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_pricing")),
        sa.UniqueConstraint(
            "organization_id",
            "provider_type",
            "model",
            name=op.f("uq_model_pricing_organization_id_provider_type_model"),
        ),
    )
    op.create_index(
        op.f("ix_model_pricing_organization_id"), "model_pricing", ["organization_id"], unique=False
    )
    op.add_column("api_usage", sa.Column("provider_id", sa.Uuid(), nullable=True))
    op.add_column("api_usage", sa.Column("agent_id", sa.Uuid(), nullable=True))
    op.add_column("api_usage", sa.Column("agent_version_id", sa.Uuid(), nullable=True))
    op.add_column("api_usage", sa.Column("user_id", sa.Uuid(), nullable=True))
    op.add_column("api_usage", sa.Column("workspace_id", sa.Uuid(), nullable=True))
    op.add_column("api_usage", sa.Column("project_id", sa.Uuid(), nullable=True))
    op.add_column("api_usage", sa.Column("workflow_id", sa.Uuid(), nullable=True))
    op.add_column("api_usage", sa.Column("command", sa.String(length=41), nullable=True))
    op.add_column(
        "api_usage", sa.Column("cached_input_tokens", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "api_usage", sa.Column("reasoning_tokens", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "api_usage", sa.Column("image_generations", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column("api_usage", sa.Column("requests", sa.Integer(), nullable=False, server_default="1"))
    op.add_column(
        "api_usage",
        sa.Column(
            "estimated_cost_usd", sa.Numeric(precision=12, scale=6), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "api_usage",
        sa.Column(
            "priced",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="a price row matched",
        ),
    )
    op.add_column(
        "api_usage",
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="ok",
            comment="ok | error | clarification | test",
        ),
    )
    op.add_column("api_usage", sa.Column("error_code", sa.String(length=80), nullable=True))
    op.create_foreign_key(
        op.f("fk_api_usage_provider_id_ai_providers"),
        "api_usage",
        "ai_providers",
        ["provider_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        op.f("fk_api_usage_agent_id_agents"), "api_usage", "agents", ["agent_id"], ["id"], ondelete="SET NULL"
    )
    op.create_foreign_key(
        op.f("fk_api_usage_user_id_users"), "api_usage", "users", ["user_id"], ["id"], ondelete="SET NULL"
    )
    op.create_foreign_key(
        op.f("fk_api_usage_workspace_id_workspaces"),
        "api_usage",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_api_usage_workspace_id_workspaces"), "api_usage", type_="foreignkey")
    op.drop_constraint(op.f("fk_api_usage_user_id_users"), "api_usage", type_="foreignkey")
    op.drop_constraint(op.f("fk_api_usage_agent_id_agents"), "api_usage", type_="foreignkey")
    op.drop_constraint(op.f("fk_api_usage_provider_id_ai_providers"), "api_usage", type_="foreignkey")
    op.drop_column("api_usage", "error_code")
    op.drop_column("api_usage", "status")
    op.drop_column("api_usage", "priced")
    op.drop_column("api_usage", "estimated_cost_usd")
    op.drop_column("api_usage", "requests")
    op.drop_column("api_usage", "image_generations")
    op.drop_column("api_usage", "reasoning_tokens")
    op.drop_column("api_usage", "cached_input_tokens")
    op.drop_column("api_usage", "command")
    op.drop_column("api_usage", "workflow_id")
    op.drop_column("api_usage", "project_id")
    op.drop_column("api_usage", "workspace_id")
    op.drop_column("api_usage", "user_id")
    op.drop_column("api_usage", "agent_version_id")
    op.drop_column("api_usage", "agent_id")
    op.drop_column("api_usage", "provider_id")
    op.drop_index(op.f("ix_model_pricing_organization_id"), table_name="model_pricing")
    op.drop_table("model_pricing")
