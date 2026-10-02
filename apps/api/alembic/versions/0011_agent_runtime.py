"""agent runtime: execution_mode + native runtime config, conversation current artifact

Revision ID: 0011
Revises: 0010
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column(
            "execution_mode",
            sa.String(length=20),
            nullable=False,
            server_default="origin_native",
            comment="origin_native (Origin receives the payload) | workspace_trigger (ChatGPT keeps the result)",
        ),
    )
    op.add_column(
        "agents",
        sa.Column(
            "native_config",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
            comment="native runtime: model, instructions, image_generation, image_options, …",
        ),
    )
    op.add_column(
        "agents",
        sa.Column(
            "native_api_key_secret_ref_id",
            sa.Uuid(),
            sa.ForeignKey("secret_refs.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("agents", sa.Column("native_api_key_preview", sa.String(length=48), nullable=True))
    op.add_column(
        "agents",
        sa.Column(
            "workspace_agent_id",
            sa.String(length=80),
            nullable=True,
            comment="agtch_… id of the ChatGPT Workspace Agent, if any",
        ),
    )
    # existing ChatGPT Workspace agents keep running in ChatGPT until an admin switches them
    op.execute(
        "UPDATE agents SET execution_mode = 'workspace_trigger' WHERE connection_type = 'chatgpt_workspace'"
    )
    op.execute(
        "UPDATE agents SET workspace_agent_id = substring(api_endpoint from 'agtch_[A-Za-z0-9_-]+') "
        "WHERE connection_type = 'chatgpt_workspace' AND api_endpoint IS NOT NULL"
    )
    op.add_column(
        "conversations",
        sa.Column(
            "current_artifact_id",
            sa.Uuid(),
            sa.ForeignKey("artifacts.id", ondelete="SET NULL"),
            nullable=True,
            comment="the last artifact an agent produced here; follow-ups receive it automatically",
        ),
    )


def downgrade() -> None:
    op.drop_column("conversations", "current_artifact_id")
    for col in (
        "workspace_agent_id",
        "native_api_key_preview",
        "native_api_key_secret_ref_id",
        "native_config",
        "execution_mode",
    ):
        op.drop_column("agents", col)
