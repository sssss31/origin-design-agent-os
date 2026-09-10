"""Test configuration.

Unit tests need nothing. API/DB tests need a PostgreSQL database reachable through
`TEST_DATABASE_URL` (default: the local instance on port 55432). The schema is created
by running the real Alembic migrations from an empty database once per session, so the
migration path itself is exercised on every test run.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

API_ROOT = Path(__file__).resolve().parents[1]
TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://pathsense_test:pathsense_test@localhost:55432/origin_test"
)

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = TEST_DB_URL
os.environ["JWT_SECRET"] = "test-jwt-secret-that-is-long-enough-for-validation-1234"
os.environ["ENCRYPTION_KEY"] = "8xrgG-Bh_ScC5uVo4VaiD1D9xLbzfTQbgtS7pl2xOmU="
os.environ["LOCAL_STORAGE_PATH"] = str(API_ROOT / ".data" / "test-storage")
os.environ["LOG_FORMAT"] = "json"
os.environ["LOG_LEVEL"] = "WARNING"
os.environ.pop("BOOTSTRAP_ADMIN_EMAIL", None)
os.environ.pop("BOOTSTRAP_ADMIN_PASSWORD", None)

from app.core.config import reset_settings_cache  # noqa: E402

reset_settings_cache()


def _database_reachable() -> bool:
    try:
        import psycopg

        with psycopg.connect(TEST_DB_URL.replace("+psycopg", ""), connect_timeout=3):
            return True
    except Exception:
        return False


DB_AVAILABLE = _database_reachable()
requires_db = pytest.mark.skipif(not DB_AVAILABLE, reason=f"test database not reachable at {TEST_DB_URL}")


def run_alembic(*args: str) -> None:
    env = {**os.environ, "DATABASE_URL": TEST_DB_URL}
    subprocess.run(
        [sys.executable, "-m", "alembic", *args], cwd=API_ROOT, env=env, check=True, capture_output=True
    )


async def _reset_schema() -> None:
    import psycopg

    async with await psycopg.AsyncConnection.connect(
        TEST_DB_URL.replace("+psycopg", ""), autocommit=True
    ) as conn:
        await conn.execute("DROP SCHEMA public CASCADE")
        await conn.execute("CREATE SCHEMA public")


@pytest.fixture(scope="session")
async def migrated_db() -> str:
    if not DB_AVAILABLE:
        pytest.skip("database not reachable")
    await _reset_schema()
    run_alembic("upgrade", "head")
    return TEST_DB_URL


@pytest.fixture(scope="session")
async def app(migrated_db: str):  # type: ignore[no-untyped-def]
    from app.main import create_app

    application = create_app()
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture(autouse=True)
async def _clean_tables(request: pytest.FixtureRequest) -> AsyncIterator[None]:
    """Truncate all tables after each DB-backed test so tests are independent."""
    yield
    if "app" not in request.fixturenames:
        return
    from sqlalchemy import text

    application = request.getfixturevalue("app")
    from app.db.base import Base

    tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    async with application.state.engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
async def client(app):  # type: ignore[no-untyped-def]
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
        yield c


class Actor:
    """A signed-in user with helpers for authenticated requests."""

    def __init__(
        self, client, email: str, access_token: str, refresh_token: str, organization_id: str | None
    ) -> None:  # type: ignore[no-untyped-def]
        self.client = client
        self.email = email
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.organization_id = organization_id

    @property
    def headers(self) -> dict[str, str]:
        h = {"Authorization": f"Bearer {self.access_token}"}
        if self.organization_id:
            h["X-Organization-Id"] = self.organization_id
        return h

    async def get(self, url: str, **kw):  # type: ignore[no-untyped-def]
        return await self.client.get(url, headers=self.headers, **kw)

    async def post(self, url: str, **kw):  # type: ignore[no-untyped-def]
        return await self.client.post(url, headers=self.headers, **kw)

    async def patch(self, url: str, **kw):  # type: ignore[no-untyped-def]
        return await self.client.patch(url, headers=self.headers, **kw)

    async def put(self, url: str, **kw):  # type: ignore[no-untyped-def]
        return await self.client.put(url, headers=self.headers, **kw)

    async def delete(self, url: str, **kw):  # type: ignore[no-untyped-def]
        return await self.client.delete(url, headers=self.headers, **kw)


@pytest.fixture
async def make_user(app, client):  # type: ignore[no-untyped-def]
    """Factory: create a user in an organization with a role, return a signed-in Actor."""
    from app.core.config import get_settings
    from app.domain.roles import Role
    from app.domain.slugs import slugify
    from app.models.identity import Organization, OrganizationMember
    from app.services.auth import AuthService
    from sqlalchemy import select

    async def _make(
        email: str, *, org: str = "Acme", role: Role = Role.MEMBER, password: str = "Password123!"
    ) -> Actor:
        async with app.state.session_factory() as session:
            svc = AuthService(session, get_settings())
            user = await svc.create_user(email=email, password=password)
            organization = await session.scalar(select(Organization).where(Organization.slug == slugify(org)))
            if organization is None:
                organization = Organization(name=org, slug=slugify(org))
                session.add(organization)
                await session.flush()
            session.add(OrganizationMember(organization_id=organization.id, user_id=user.id, role=role))
            await session.commit()
            org_id = str(organization.id)
        res = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert res.status_code == 200, res.text
        body = res.json()
        return Actor(client, email, body["access_token"], body["refresh_token"], org_id)

    return _make
