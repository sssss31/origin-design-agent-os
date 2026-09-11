"""The one place that maps settings to adapter implementations.

To add a backend: implement the port in `app/adapters/<kind>/<name>.py`, add a branch here,
and add the literal to the matching `Settings` field. Nothing else changes.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.ports.embeddings import EmbeddingProvider
from app.ports.events import EventBus
from app.ports.queue import JobQueue
from app.ports.runner import AgentRunner
from app.ports.scheduler import WorkflowScheduler
from app.ports.secrets import SecretStore
from app.ports.storage import ObjectStorage


@dataclass(slots=True)
class Adapters:
    storage: ObjectStorage
    secrets: SecretStore
    queue: JobQueue
    events: EventBus
    scheduler: WorkflowScheduler
    embeddings: EmbeddingProvider
    runners: dict[str, AgentRunner]

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

    key = settings.encryption_key or Fernet.generate_key().decode()  # ephemeral key in dev only
    return FernetSecretStore(key, session_factory)


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


def build_runners(settings: Settings) -> dict[str, AgentRunner]:
    """Provider type → runner. Provider rows (Phase 2) pick one of these by `type`."""
    from app.adapters.runners.echo import EchoRunner
    from app.adapters.runners.openai_agents import OpenAIAgentsRunner

    runners: dict[str, AgentRunner] = {
        "echo": EchoRunner(),
        "openai": OpenAIAgentsRunner(
            trace_include_sensitive_data=settings.openai_agents_trace_include_sensitive_data
        ),
    }
    return runners


def build_adapters(settings: Settings, session_factory: async_sessionmaker[AsyncSession]) -> Adapters:
    return Adapters(
        storage=build_storage(settings),
        secrets=build_secret_store(settings, session_factory),
        queue=build_queue(settings),
        events=build_event_bus(settings),
        scheduler=build_scheduler(settings),
        embeddings=build_embeddings(settings),
        runners=build_runners(settings),
    )
