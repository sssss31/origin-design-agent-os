"""Operational CLI: `python -m app.cli --help`."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

import typer

from app.core.config import get_settings

cli = typer.Typer(help="Origin Design Agent OS — API operations", no_args_is_help=True)
API_ROOT = Path(__file__).resolve().parents[1]


@cli.command()
def check_config() -> None:
    """Validate settings for the current APP_ENV and print the selected adapters (no secrets)."""
    s = get_settings()
    typer.echo(
        f"env={s.app_env} storage={s.storage_backend} queue={s.queue_backend} events={s.event_bus_backend}"
    )
    typer.echo(f"scheduler={s.workflow_scheduler} secrets={s.secret_backend} cors={s.cors_origins}")
    typer.echo("ok")


@cli.command()
def migrate(revision: str = "head") -> None:
    """Run Alembic migrations."""
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", revision], cwd=API_ROOT, check=True)  # noqa: S603


@cli.command()
def bootstrap_admin(
    email: str = typer.Option(..., prompt=True),
    password: str = typer.Option(..., prompt=True, hide_input=True, confirmation_prompt=True),
    organization: str = typer.Option("Origin", help="Organization name (created if missing)"),
) -> None:
    """Create (or promote) the first administrator and their organization."""

    async def _run() -> None:
        from app.db.session import create_engine, create_session_factory
        from app.services.auth import AuthService

        settings = get_settings()
        engine = create_engine(settings)
        factory = create_session_factory(engine)
        async with factory() as session:
            user, org, created = await AuthService(session, settings).bootstrap_admin(
                email=email, password=password, organization_name=organization
            )
            await session.commit()
        await engine.dispose()
        verb = "created" if created else "updated"
        typer.echo(f"{verb} admin {user.email} in organization '{org.name}' ({org.id})")

    asyncio.run(_run())


@cli.command()
def seed_design_agents(
    email: str = typer.Option(..., help="Admin user whose organization receives the seed"),
    provider_type: str = typer.Option("openai", help="openai | echo"),
    model: str | None = typer.Option(None, help="Model id to allowlist and assign (default: gpt-5 / echo-1)"),
    no_publish: bool = typer.Option(False, help="Leave the seeded agents as drafts"),
) -> None:
    """Seed built-in tools, the reusable skills and the eight design agents (idempotent)."""

    async def _run() -> None:
        import uuid

        from sqlalchemy import select

        from app.core.authz import AuthContext
        from app.db.session import create_engine, create_session_factory
        from app.domain.roles import Role
        from app.models.identity import OrganizationMember, User
        from app.seeds.design_agents import seed_design_agents as _seed

        settings = get_settings()
        engine = create_engine(settings)
        factory = create_session_factory(engine)
        async with factory() as session:
            user = await session.scalar(select(User).where(User.email == email.lower()))
            if user is None:
                raise typer.BadParameter(f"no user {email}")
            membership = await session.scalar(
                select(OrganizationMember).where(
                    OrganizationMember.user_id == user.id, OrganizationMember.role == Role.ADMIN
                )
            )
            if membership is None:
                raise typer.BadParameter(f"{email} is not an organization admin")
            ctx = AuthContext(
                user=user,
                memberships={membership.organization_id: Role.ADMIN},
                organization_id=membership.organization_id,
            )
            stats = await _seed(
                session, ctx, provider_type=provider_type, model=model, publish=not no_publish
            )
            await session.commit()
            _ = uuid
        await engine.dispose()
        typer.echo(f"seeded: {stats}")

    asyncio.run(_run())


@cli.command()
def generate_keys() -> None:
    """Print fresh JWT_SECRET and ENCRYPTION_KEY values for a new deployment."""
    import secrets

    from cryptography.fernet import Fernet

    typer.echo(f"JWT_SECRET={secrets.token_urlsafe(48)}")
    typer.echo(f"ENCRYPTION_KEY={Fernet.generate_key().decode()}")


if __name__ == "__main__":
    cli()
