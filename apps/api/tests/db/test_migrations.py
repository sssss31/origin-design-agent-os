"""Migrations must run from an empty database, downgrade cleanly, and match the models."""

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect

from tests.conftest import requires_db, run_alembic

pytestmark = requires_db

EXPECTED_TABLES = {
    "users",
    "organizations",
    "organization_members",
    "refresh_tokens",
    "workspaces",
    "workspace_members",
    "projects",
    "project_rules",
    "audit_logs",
    "secret_refs",
    "ai_providers",
    "agents",
    "agent_versions",
    "skills",
    "tools",
    "conversations",
    "messages",
    "message_attachments",
    "assets",
    "asset_versions",
    "artifacts",
    "artifact_versions",
    "alembic_version",
}


async def test_schema_matches_models_and_roundtrips(app) -> None:  # type: ignore[no-untyped-def]
    from app.db.base import Base

    engine = app.state.engine

    def _inspect(conn):  # type: ignore[no-untyped-def]
        names = set(inspect(conn).get_table_names())
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
        return names, diff

    async with engine.connect() as conn:
        names, diff = await conn.run_sync(_inspect)
    assert EXPECTED_TABLES <= names
    assert diff == [], f"models and migrations differ: {diff}"

    run_alembic("downgrade", "base")
    async with engine.connect() as conn:
        names_after, _ = await conn.run_sync(_inspect)
    assert names_after <= {"alembic_version"}
    run_alembic("upgrade", "head")
    async with engine.connect() as conn:
        names_final, _ = await conn.run_sync(_inspect)
    assert EXPECTED_TABLES <= names_final
