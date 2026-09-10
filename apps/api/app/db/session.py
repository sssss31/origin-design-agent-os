"""Async engine + session factory. One engine per process, created at startup."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    kwargs: dict[str, object] = {"echo": settings.database_echo, "pool_pre_ping": True}
    if not settings.database_url.startswith("sqlite"):
        kwargs["pool_size"] = settings.database_pool_size
        kwargs["max_overflow"] = settings.database_pool_size
    return create_async_engine(settings.database_url, **kwargs)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency. Commits on success, rolls back on error."""
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
