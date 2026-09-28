"""BOOTSTRAP_ADMIN_SYNC_PASSWORD: recover a forgotten admin password from the environment."""

from __future__ import annotations

from app.core.config import get_settings
from app.services.auth import AuthService

from tests.conftest import requires_db

pytestmark = requires_db


async def test_bootstrap_sync_resets_existing_admin_password(app, client) -> None:  # type: ignore[no-untyped-def]
    settings = get_settings()
    async with app.state.session_factory() as session:
        svc = AuthService(session, settings)
        _, _, created = await svc.bootstrap_admin(
            email="boot@example.com", password="FirstPassword123!", organization_name="Boot Org"
        )
        assert created
        # default: an existing admin keeps their password
        await svc.bootstrap_admin(
            email="boot@example.com", password="SecondPassword123!", organization_name="Boot Org"
        )
        await session.commit()
    assert (
        await client.post(
            "/api/v1/auth/login", json={"email": "boot@example.com", "password": "FirstPassword123!"}
        )
    ).status_code == 200
    assert (
        await client.post(
            "/api/v1/auth/login", json={"email": "boot@example.com", "password": "SecondPassword123!"}
        )
    ).status_code == 401
    async with app.state.session_factory() as session:
        _, _, created = await AuthService(session, settings).bootstrap_admin(
            email="boot@example.com",
            password="SecondPassword123!",
            organization_name="Boot Org",
            sync_password=True,
        )
        assert not created
        await session.commit()
    assert (
        await client.post(
            "/api/v1/auth/login", json={"email": "boot@example.com", "password": "SecondPassword123!"}
        )
    ).status_code == 200
    assert (
        await client.post(
            "/api/v1/auth/login", json={"email": "boot@example.com", "password": "FirstPassword123!"}
        )
    ).status_code == 401
