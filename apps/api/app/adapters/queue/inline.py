"""In-process queue: handlers run as background asyncio tasks in the API process.

Good for development, tests and single-replica deployments. Because run state is
durable in Postgres, an API restart can re-enqueue unfinished runs on startup.
"""

from __future__ import annotations

import asyncio
import uuid

from app.core.logging import get_logger
from app.ports.queue import Job, JobHandler

log = get_logger("queue.inline")


class InlineQueue:
    name = "inline"

    def __init__(self) -> None:
        self._handlers: dict[str, JobHandler] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        self._seen: set[str] = set()

    def register(self, job_type: str, handler: JobHandler) -> None:
        self._handlers[job_type] = handler

    async def enqueue(self, job: Job) -> str:
        handler = self._handlers.get(job.type)
        if handler is None:
            raise LookupError(f"no handler registered for job type {job.type!r}")
        job_id = job.idempotency_key or uuid.uuid4().hex
        if job.idempotency_key and job.idempotency_key in self._seen:
            return job_id
        self._seen.add(job_id)

        async def _run() -> None:
            try:
                await handler(job)
            except Exception:
                log.exception("inline_job_failed", job_type=job.type, job_id=job_id)
            finally:
                self._seen.discard(job_id)

        task = asyncio.create_task(_run(), name=f"job:{job.type}:{job_id}")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return job_id

    async def drain(self) -> None:
        """Wait for in-flight jobs (tests and graceful shutdown)."""
        if self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def health(self) -> bool:
        return True
