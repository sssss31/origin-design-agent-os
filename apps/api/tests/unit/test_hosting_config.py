"""Hosting-friendly settings: managed Postgres URLs and platform-generated secrets."""

from __future__ import annotations

from app.core.config import Settings
from cryptography.fernet import Fernet


def test_managed_postgres_url_is_normalised() -> None:
    s = Settings(database_url="postgres://u:p@db.internal:5432/origin", _env_file=None)
    assert s.database_url == "postgresql+psycopg://u:p@db.internal:5432/origin"
    s = Settings(database_url="postgresql://u:p@h/d", _env_file=None)
    assert s.database_url.startswith("postgresql+psycopg://")


def test_encryption_key_accepts_fernet_or_long_secret() -> None:
    real = Fernet.generate_key().decode()
    assert Settings(encryption_key=real, _env_file=None).fernet_key == real
    derived = Settings(encryption_key="x" * 48, _env_file=None).fernet_key
    Fernet(derived.encode())  # valid key derived from a platform-generated string
    assert derived == Settings(encryption_key="x" * 48, _env_file=None).fernet_key  # deterministic


def test_short_non_fernet_key_is_rejected() -> None:
    import pytest

    with pytest.raises(ValueError, match="ENCRYPTION_KEY"):
        Settings(encryption_key="too-short", _env_file=None)


def test_single_instance_production_profile() -> None:
    base = {
        "app_env": "production",
        "jwt_secret": "j" * 40,
        "encryption_key": "e" * 40,
        "allowed_origins": "https://app.example.com",
        "outbound_allow_http": False,
        "bootstrap_admin_password": "p" * 16,
        "_env_file": None,
    }
    import pytest

    with pytest.raises(ValueError, match="SINGLE_INSTANCE"):
        Settings(**base)
    s = Settings(single_instance=True, **base)
    assert s.queue_backend == "inline" and s.storage_backend == "local"


def test_serverless_rejects_supabase_direct_connection() -> None:
    import pytest

    with pytest.raises(ValueError, match="pooler"):
        Settings(
            serverless=True,
            database_url="postgresql://postgres:pw@db.abc.supabase.co:5432/postgres",
            _env_file=None,
        )
    ok = Settings(
        serverless=True,
        database_url="postgresql://postgres.abc:pw@aws-0-ap-south-1.pooler.supabase.com:6543/postgres",
        _env_file=None,
    )
    assert ok.database_url.startswith("postgresql+psycopg://")


def test_marketplace_postgres_url_is_accepted(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv(
        "POSTGRES_URL", "postgres://u:p@ep-x-pooler.aws.neon.tech/neondb?sslmode=require&supa=base-pooler.x"
    )
    s = Settings(_env_file=None)
    assert s.database_url == "postgresql+psycopg://u:p@ep-x-pooler.aws.neon.tech/neondb?sslmode=require"


def test_database_url_whitespace_and_quotes_are_stripped() -> None:
    s = Settings(database_url=' "postgresql://u:p@h:6543/postgres"\n', _env_file=None)
    assert s.database_url == "postgresql+psycopg://u:p@h:6543/postgres"


def test_alembic_url_escaping_survives_configparser() -> None:
    """A URL-encoded password ("%40") must round-trip through alembic's configparser-backed config."""
    from alembic.config import Config

    url = "postgresql+psycopg://postgres.ref:Pa%40ss@aws-0-x.pooler.supabase.com:6543/postgres"
    cfg = Config()
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    assert cfg.get_main_option("sqlalchemy.url") == url


def test_migration_fast_path_skips_when_at_head(migrated_db) -> None:  # type: ignore[no-untyped-def]
    """A cold start on an up-to-date database must not run alembic (one SELECT and done)."""
    import time

    from app.core.migrate import _head_revision, _upgrade_sync

    assert _head_revision()
    started = time.perf_counter()
    _upgrade_sync(Settings(database_url=migrated_db, _env_file=None))
    assert time.perf_counter() - started < 1.5
