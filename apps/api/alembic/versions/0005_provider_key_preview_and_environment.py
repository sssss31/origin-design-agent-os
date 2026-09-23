"""provider key preview and environment

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-23 07:28:21.801295+00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ai_providers",
        sa.Column(
            "key_preview",
            sa.String(length=48),
            nullable=True,
            comment="masked form e.g. sk-proj-••••••••7Xk2; never the value",
        ),
    )
    op.add_column(
        "ai_providers",
        sa.Column(
            "environment",
            sa.String(length=20),
            nullable=False,
            server_default="production",
            comment="production | staging | development",
        ),
    )


def downgrade() -> None:
    op.drop_column("ai_providers", "environment")
    op.drop_column("ai_providers", "key_preview")
