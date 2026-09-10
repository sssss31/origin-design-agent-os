from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class EventBus(Protocol):
    """Live fan-out of execution events to SSE subscribers.

    Persistence is NOT this port's job: `execution_events` rows are written first, then
    published here. Subscribers that reconnect replay from the database.
    """

    name: str

    async def publish(self, channel: str, event: dict[str, Any]) -> None: ...

    def subscribe(self, channel: str) -> AsyncIterator[dict[str, Any]]: ...

    async def health(self) -> bool: ...
