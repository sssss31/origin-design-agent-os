"""sticky agent and agent sessions

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-23 08:40:34.150993+00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_sessions",
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("provider_type", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column(
            "input_list",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="provider transcript items",
        ),
        sa.Column("turns", sa.Integer(), nullable=False),
        sa.Column("chars", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["agent_id"], ["agents.id"], name=op.f("fk_agent_sessions_agent_id_agents"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_agent_sessions_conversation_id_conversations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_sessions")),
        sa.UniqueConstraint(
            "conversation_id", "agent_id", name=op.f("uq_agent_sessions_conversation_id_agent_id")
        ),
    )
    op.create_index(op.f("ix_agent_sessions_agent_id"), "agent_sessions", ["agent_id"], unique=False)
    op.create_index(
        op.f("ix_agent_sessions_conversation_id"), "agent_sessions", ["conversation_id"], unique=False
    )
    op.add_column(
        "conversations",
        sa.Column(
            "active_agent_id",
            sa.Uuid(),
            nullable=True,
            comment="agent that plain messages go to after a /command activated it",
        ),
    )
    op.create_foreign_key(
        op.f("fk_conversations_active_agent_id_agents"),
        "conversations",
        "agents",
        ["active_agent_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_conversations_active_agent_id_agents"), "conversations", type_="foreignkey")
    op.drop_column("conversations", "active_agent_id")
    op.drop_index(op.f("ix_agent_sessions_conversation_id"), table_name="agent_sessions")
    op.drop_index(op.f("ix_agent_sessions_agent_id"), table_name="agent_sessions")
    op.drop_table("agent_sessions")
