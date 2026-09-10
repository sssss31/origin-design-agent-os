"""Redis pub/sub event bus so every API replica can serve SSE for any run."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any


class RedisEventBus:
    name = "redis"

    def __init__(self, redis_url: str, *, namespace: str = "origin:events") -> None:
        import redis.asyncio as aioredis

        self._redis = aioredis.from_url(redis_url, decode_responses=True)
        self._ns = namespace

    def _channel(self, channel: str) -> str:
        return f"{self._ns}:{channel}"

    async def publish(self, channel: str, event: dict[str, Any]) -> None:
        await self._redis.publish(self._channel(channel), json.dumps(event))

    async def subscribe(self, channel: str) -> AsyncIterator[dict[str, Any]]:
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(self._channel(channel))
        try:
            async for message in pubsub.listen():
                if message.get("type") == "message":
                    yield json.loads(message["data"])
        finally:
            await pubsub.unsubscribe(self._channel(channel))
            await pubsub.aclose()

    async def health(self) -> bool:
        try:
            return bool(await self._redis.ping())
        except Exception:
            return False
