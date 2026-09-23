"""existing agent connections

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-23 09:30:20.666606+00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_sessions",
        sa.Column(
            "provider_session_id",
            sa.String(length=200),
            nullable=True,
            comment="native session (previous_response_id / thread_id) of the agent",
        ),
    )
    op.add_column(
        "agents",
        sa.Column(
            "connection_type",
            sa.String(length=30),
            nullable=False,
            server_default="origin",
            comment="origin (prompt built here) | openai_responses | http (existing agent API)",
        ),
    )
    op.add_column("agents", sa.Column("api_endpoint", sa.String(length=2000), nullable=True))
    op.add_column("agents", sa.Column("api_key_secret_ref_id", sa.Uuid(), nullable=True))
    op.add_column(
        "agents",
        sa.Column("api_key_preview", sa.String(length=48), nullable=True, comment="masked, never the key"),
    )
    op.add_column(
        "agents",
        sa.Column(
            "connection_config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
            comment="model / prompt_id / request+response mapping",
        ),
    )
    op.add_column(
        "agents",
        sa.Column("connection_status", sa.String(length=20), nullable=False, server_default="unknown"),
    )
    op.add_column("agents", sa.Column("connection_message", sa.Text(), nullable=True))
    op.add_column("agents", sa.Column("connection_tested_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        op.f("fk_agents_api_key_secret_ref_id_secret_refs"),
        "agents",
        "secret_refs",
        ["api_key_secret_ref_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_agents_api_key_secret_ref_id_secret_refs"), "agents", type_="foreignkey")
    op.drop_column("agents", "connection_tested_at")
    op.drop_column("agents", "connection_message")
    op.drop_column("agents", "connection_status")
    op.drop_column("agents", "connection_config")
    op.drop_column("agents", "api_key_preview")
    op.drop_column("agents", "api_key_secret_ref_id")
    op.drop_column("agents", "api_endpoint")
    op.drop_column("agents", "connection_type")
    op.drop_column("agent_sessions", "provider_session_id")
