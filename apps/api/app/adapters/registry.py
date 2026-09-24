"""The one place that maps settings to adapter implementations.

To add a backend: implement the port in `app/adapters/<kind>/<name>.py`, add a branch here,
and add the literal to the matching `Settings` field. Nothing else changes.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.ports.embeddings import EmbeddingProvider
from app.ports.events import EventBus
from app.ports.queue import JobQueue
from app.ports.runner import AgentRunner
from app.ports.scheduler import WorkflowScheduler
from app.ports.secrets import SecretStore
from app.ports.storage import ObjectStorage
from app.providers.base import AIProvider


@dataclass(slots=True)
class Adapters:
    storage: ObjectStorage
    secrets: SecretStore
    queue: JobQueue
    events: EventBus
    scheduler: WorkflowScheduler
    embeddings: EmbeddingProvider
    runners: dict[str, AgentRunner]
    providers: dict[str, AIProvider] = field(default_factory=dict)
    http_transport: Any = None  # tests inject an httpx.MockTransport for custom integrations

    async def health(self) -> dict[str, bool]:
        return {
            "storage": await self.storage.health(),
            "secrets": await self.secrets.health(),
            "queue": await self.queue.health(),
            "events": await self.events.health(),
        }


def build_storage(settings: Settings) -> ObjectStorage:
    if settings.storage_backend == "s3":
        from app.adapters.storage.s3 import S3Storage

        return S3Storage(
            bucket=settings.object_storage_bucket,
            endpoint_url=settings.object_storage_endpoint,
            public_endpoint_url=settings.object_storage_public_endpoint,
            access_key=settings.object_storage_access_key,
            secret_key=settings.object_storage_secret_key,
            region=settings.object_storage_region,
        )
    from app.adapters.storage.local_fs import LocalFSStorage

    return LocalFSStorage(
        settings.local_storage_path, signing_key=settings.jwt_secret, public_base_url=settings.api_prefix
    )


def build_secret_store(settings: Settings, session_factory: async_sessionmaker[AsyncSession]) -> SecretStore:
    if settings.secret_backend == "env":
        from app.adapters.secrets.env import EnvSecretStore

        return EnvSecretStore()
    from cryptography.fernet import Fernet

    from app.adapters.secrets.fernet_db import FernetSecretStore

    key = settings.fernet_key or _development_key(Fernet.generate_key)
    return FernetSecretStore(key, session_factory)


def _development_key(generate: Callable[[], bytes]) -> str:
    """Outside production a missing ENCRYPTION_KEY is tolerated, but the key must survive
    restarts (uvicorn --reload) or every stored credential becomes unreadable. Keep it in a
    git-ignored, owner-only file next to the app."""
    path = Path(".data") / "dev-encryption.key"
    try:
        if path.exists():
            return path.read_text().strip()
        path.parent.mkdir(parents=True, exist_ok=True)
        key = generate().decode()
        path.write_text(key)
        path.chmod(0o600)
        return key
    except OSError:
        return generate().decode()


def build_queue(settings: Settings) -> JobQueue:
    if settings.queue_backend == "redis":
        from app.adapters.queue.redis_queue import RedisQueue

        if not settings.redis_url:
            raise ValueError("REDIS_URL is required for QUEUE_BACKEND=redis")
        return RedisQueue(settings.redis_url)
    from app.adapters.queue.inline import InlineQueue

    return InlineQueue()


def build_event_bus(settings: Settings) -> EventBus:
    if settings.event_bus_backend == "redis":
        from app.adapters.events.redis_bus import RedisEventBus

        if not settings.redis_url:
            raise ValueError("REDIS_URL is required for EVENT_BUS_BACKEND=redis")
        return RedisEventBus(settings.redis_url)
    from app.adapters.events.memory import InMemoryEventBus

    return InMemoryEventBus()


def build_scheduler(settings: Settings) -> WorkflowScheduler:
    if settings.workflow_scheduler == "dag":
        from app.adapters.scheduler.dag import DagScheduler

        return DagScheduler()
    from app.adapters.scheduler.sequential import SequentialScheduler

    return SequentialScheduler()


def build_embeddings(settings: Settings) -> EmbeddingProvider:
    from app.adapters.embeddings.null import NullEmbeddings

    # Phase 4 adds OpenAIEmbeddings behind settings.embeddings_backend == "openai".
    return NullEmbeddings()


def build_providers(settings: Settings) -> dict[str, AIProvider]:
    """Provider type → adapter. Provider rows pick one of these by `type`; add new vendors here."""
    from app.providers.echo_provider import EchoProvider
    from app.providers.openai_provider import OpenAIProvider

    return {
        "echo": EchoProvider(),
        "openai": OpenAIProvider(
            trace_include_sensitive_data=settings.openai_agents_trace_include_sensitive_data,
            max_attempts=settings.provider_retry_attempts,
            backoff_seconds=settings.provider_retry_backoff_seconds,
        ),
    }


def build_runners(settings: Settings) -> dict[str, AgentRunner]:
    """Kept for callers that only need the raw runner; derived from the provider adapters."""
    return {t: p.runner for t, p in build_providers(settings).items()}


def build_adapters(settings: Settings, session_factory: async_sessionmaker[AsyncSession]) -> Adapters:
    providers = build_providers(settings)
    return Adapters(
        storage=build_storage(settings),
        secrets=build_secret_store(settings, session_factory),
        queue=build_queue(settings),
        events=build_event_bus(settings),
        scheduler=build_scheduler(settings),
        embeddings=build_embeddings(settings),
        runners={t: p.runner for t, p in providers.items()},
        providers=providers,
    )
