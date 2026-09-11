"""Per-user (or per-IP) sliding-window rate limit (spec §16 P8).

In-memory by default (single replica); with REDIS_URL the counters live in Redis so every
replica shares them. Health endpoints and the SSE stream are exempt.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Any

from starlette.datastructures import Headers

from app.core.config import Settings
from app.core.logging import get_logger

log = get_logger("ratelimit")

EXEMPT_SUFFIXES = ("/healthz", "/readyz", "/events")


class RateLimiter:
    def __init__(self, settings: Settings) -> None:
        self.limit = settings.rate_limit_per_minute
        self.window = 60.0
        self._local: dict[str, deque[float]] = {}
        self._redis: Any = None
        if settings.redis_url and self.limit > 0:
            try:
                import redis.asyncio as aioredis

                self._redis = aioredis.from_url(settings.redis_url, decode_responses=True)
            except Exception:  # pragma: no cover - redis optional
                self._redis = None

    async def check(self, key: str) -> tuple[bool, int]:
        """Returns (allowed, retry_after_seconds)."""
        if self.limit <= 0:
            return True, 0
        now = time.time()
        if self._redis is not None:
            try:
                bucket = f"origin:rl:{key}:{int(now // self.window)}"
                count = await self._redis.incr(bucket)
                if count == 1:
                    await self._redis.expire(bucket, int(self.window) + 1)
                if count > self.limit:
                    return False, int(self.window - (now % self.window)) + 1
                return True, 0
            except Exception as exc:  # fall back to local limiting if redis is unavailable
                log.warning("ratelimit_redis_unavailable", error=type(exc).__name__)
        q = self._local.setdefault(key, deque())
        while q and q[0] <= now - self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False, int(q[0] + self.window - now) + 1
        q.append(now)
        if len(self._local) > 10000:  # bound memory
            for k in [k for k, v in self._local.items() if not v or v[-1] < now - self.window]:
                self._local.pop(k, None)
        return True, 0


class RateLimitMiddleware:
    def __init__(self, app: Any, limiter: RateLimiter) -> None:
        self.app = app
        self.limiter = limiter

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http" or scope["path"].endswith(EXEMPT_SUFFIXES) or self.limiter.limit <= 0:
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        auth = headers.get("authorization", "")
        client = scope.get("client")
        key = (
            ("tok:" + auth[-24:])
            if auth.lower().startswith("bearer ")
            else ("ip:" + (client[0] if client else "unknown"))
        )
        allowed, retry_after = await self.limiter.check(key)
        if allowed:
            await self.app(scope, receive, send)
            return
        body = (
            b'{"error":{"code":"rate_limited","message":"Too many requests",'
            b'"details":null,"request_id":null}}'
        )
        await send(
            {
                "type": "http.response.start",
                "status": 429,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"retry-after", str(retry_after).encode()),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
