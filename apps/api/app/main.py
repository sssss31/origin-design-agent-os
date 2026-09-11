"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.adapters.registry import build_adapters
from app.api.v1.health import router as root_health_router
from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestContextMiddleware
from app.core.ratelimit import RateLimiter, RateLimitMiddleware
from app.db.session import create_engine, create_session_factory

log = get_logger("startup")


async def _dev_bootstrap(app: FastAPI, settings: Settings) -> None:
    """Development convenience: create the first admin from env vars. Refused in production by Settings."""
    if not (settings.bootstrap_admin_email and settings.bootstrap_admin_password):
        return
    from app.services.auth import AuthService

    async with app.state.session_factory() as session:
        try:
            _, _, created = await AuthService(session, settings).bootstrap_admin(
                email=settings.bootstrap_admin_email,
                password=settings.bootstrap_admin_password,
                organization_name=settings.bootstrap_organization_name,
            )
            await session.commit()
            log.info("bootstrap_admin", email=settings.bootstrap_admin_email, created=created)
        except Exception as exc:  # tables may not exist yet; report instead of crashing
            await session.rollback()
            log.warning("bootstrap_admin_skipped", reason=f"{type(exc).__name__}: {str(exc)[:200]}")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings)
        app.state.settings = settings
        app.state.engine = engine
        app.state.session_factory = create_session_factory(engine)
        app.state.adapters = build_adapters(settings, app.state.session_factory)
        from app.workers.recovery import recover_runs
        from app.workers.run_executor import RunExecutor

        app.state.adapters.queue.register(
            "run.execute", RunExecutor(app.state.session_factory, app.state.adapters, settings).handle
        )
        await recover_runs(app.state.session_factory, app.state.adapters, settings)
        await _dev_bootstrap(app, settings)
        log.info(
            "startup",
            env=settings.app_env,
            storage=app.state.adapters.storage.name,
            queue=app.state.adapters.queue.name,
            events=app.state.adapters.events.name,
            scheduler=app.state.adapters.scheduler.name,
        )
        try:
            yield
        finally:
            drain = getattr(app.state.adapters.queue, "drain", None)
            if drain:
                await drain()
            await engine.dispose()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
        docs_url="/docs" if not settings.is_production_like else None,
        redoc_url=None,
        openapi_url=f"{settings.api_prefix}/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Organization-Id", "X-Request-Id", "Last-Event-ID"],
        expose_headers=["X-Request-Id"],
    )
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(RateLimitMiddleware, limiter=RateLimiter(settings))
    register_exception_handlers(app)
    app.include_router(root_health_router)  # /healthz, /readyz for load balancers
    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()
