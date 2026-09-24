"""Queue for serverless hosting (Vercel Functions): nothing runs in the background after a
response is sent, so `enqueue` only records intent. The SSE endpoint that the client opens
right after creating a run executes it in-process while streaming (see api/v1/runs.py)."""

from __future__ import annotations

import uuid

from app.ports.queue import Job, JobHandler


class DeferredQueue:
    name = "deferred"

    def __init__(self) -> None:
        self._handlers: dict[str, JobHandler] = {}

    def register(self, job_type: str, handler: JobHandler) -> None:
        self._handlers[job_type] = handler

    async def enqueue(self, job: Job) -> str:
        if job.type not in self._handlers:
            raise LookupError(f"no handler registered for job type {job.type!r}")
        return job.idempotency_key or uuid.uuid4().hex

    async def drain(self) -> None:
        return None

    async def health(self) -> bool:
        return True
