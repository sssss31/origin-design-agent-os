from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(slots=True)
class Job:
    type: str
    payload: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str | None = None
    attempts: int = 0


JobHandler = Callable[[Job], Awaitable[None]]


@runtime_checkable
class JobQueue(Protocol):
    """Durable-enough job hand-off between the API and workers.

    `InlineQueue` executes handlers in-process (development/tests). `RedisQueue` hands
    jobs to separate worker processes. Run state itself is always durable in Postgres, so
    a lost job is recoverable by re-enqueueing the run id.
    """

    name: str

    def register(self, job_type: str, handler: JobHandler) -> None: ...

    async def enqueue(self, job: Job) -> str: ...

    async def health(self) -> bool: ...
