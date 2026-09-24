"""Run alembic migrations from inside the app (serverless/first-request startup).

A Postgres advisory lock serialises concurrent cold starts; alembic itself is run in a worker
thread because its env.py owns an event loop."""

from __future__ import annotations

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.core.config import Settings
from app.core.logging import get_logger

log = get_logger(__name__)
LOCK_ID = 727_001
API_ROOT = Path(__file__).resolve().parents[2]


def _upgrade_sync(settings: Settings) -> None:
    import psycopg

    dsn = settings.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("SELECT pg_advisory_lock(%s)", (LOCK_ID,))
        try:
            cfg = Config(str(API_ROOT / "alembic.ini"))
            cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
            command.upgrade(cfg, "head")
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_ID,))


async def migrate_to_head(settings: Settings) -> None:
    log.info("migrations_start")
    await asyncio.to_thread(_upgrade_sync, settings)
    log.info("migrations_done")
