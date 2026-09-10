"""Redis list-backed queue with a reliable-queue pattern (BLMOVE to a processing list).

Workers (`app/workers/main.py`) call `run_worker()`. Jobs that a crashed worker left in
the processing list are re-queued by `requeue_stale()` on worker start.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from app.core.logging import get_logger
from app.ports.queue import Job, JobHandler

log = get_logger("queue.redis")


class RedisQueue:
    name = "redis"

    def __init__(self, redis_url: str, *, namespace: str = "origin:jobs") -> None:
        import redis.asyncio as aioredis

        self._redis = aioredis.from_url(redis_url, decode_responses=True)
        self._ns = namespace
        self._handlers: dict[str, JobHandler] = {}

    @property
    def _pending(self) -> str:
        return f"{self._ns}:pending"

    @property
    def _processing(self) -> str:
        return f"{self._ns}:processing"

    def register(self, job_type: str, handler: JobHandler) -> None:
        self._handlers[job_type] = handler

    async def enqueue(self, job: Job) -> str:
        job_id = job.idempotency_key or uuid.uuid4().hex
        if job.idempotency_key:
            added = await self._redis.sadd(f"{self._ns}:inflight", job.idempotency_key)
            if not added:
                return job_id
        body = json.dumps({"id": job_id, "type": job.type, "payload": job.payload, "attempts": job.attempts})
        await self._redis.lpush(self._pending, body)
        return job_id

    async def requeue_stale(self) -> int:
        moved = 0
        while await self._redis.rpoplpush(self._processing, self._pending):
            moved += 1
        return moved

    async def run_worker(self, *, stop: asyncio.Event | None = None) -> None:
        stop = stop or asyncio.Event()
        await self.requeue_stale()
        while not stop.is_set():
            raw: Any = await self._redis.blmove(
                self._pending, self._processing, timeout=2, src="RIGHT", dest="LEFT"
            )
            if raw is None:
                continue
            data = json.loads(raw)
            job = Job(
                type=data["type"],
                payload=data["payload"],
                idempotency_key=data["id"],
                attempts=data.get("attempts", 0),
            )
            handler = self._handlers.get(job.type)
            try:
                if handler is None:
                    raise LookupError(f"no handler for {job.type}")
                await handler(job)
            except Exception:
                log.exception("redis_job_failed", job_type=job.type, job_id=job.idempotency_key)
            finally:
                await self._redis.lrem(self._processing, 1, raw)
                await self._redis.srem(f"{self._ns}:inflight", data["id"])

    async def health(self) -> bool:
        try:
            return bool(await self._redis.ping())
        except Exception:
            return False
