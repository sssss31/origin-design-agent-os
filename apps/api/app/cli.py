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
def generate_keys() -> None:
    """Print fresh JWT_SECRET and ENCRYPTION_KEY values for a new deployment."""
    import secrets

    from cryptography.fernet import Fernet

    typer.echo(f"JWT_SECRET={secrets.token_urlsafe(48)}")
    typer.echo(f"ENCRYPTION_KEY={Fernet.generate_key().decode()}")


if __name__ == "__main__":
    cli()
