"""In-process pub/sub for live execution events (single API replica)."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Any


class InMemoryEventBus:
    name = "memory"

    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)

    async def publish(self, channel: str, event: dict[str, Any]) -> None:
        for queue in list(self._subscribers.get(channel, ())):
            queue.put_nowait(event)

    async def subscribe(self, channel: str) -> AsyncIterator[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers[channel].add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._subscribers[channel].discard(queue)
            if not self._subscribers[channel]:
                self._subscribers.pop(channel, None)

    def subscriber_count(self, channel: str) -> int:
        return len(self._subscribers.get(channel, ()))

    async def health(self) -> bool:
        return True
