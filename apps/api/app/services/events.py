"""Durable execution events (ADR 0003).

`EventRecorder` appends rows inside the executor's transaction; after the transaction commits
the same events are published on the EventBus for live SSE subscribers. Reconnecting clients
replay from the database with `Last-Event-ID`, so nothing is lost if a publish is missed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.events import EventType, SafeEventPayload
from app.models.workflows import ExecutionEvent
from app.ports.events import EventBus

TERMINAL_EVENTS = frozenset({EventType.RUN_COMPLETED, EventType.RUN_FAILED, EventType.RUN_CANCELLED})


def event_to_wire(ev: ExecutionEvent) -> dict[str, Any]:
    return {
        "run_id": str(ev.run_id),
        "sequence_no": ev.sequence_no,
        "type": ev.type,
        "occurred_at": ev.occurred_at.isoformat() if ev.occurred_at else datetime.now(UTC).isoformat(),
        "node_run_id": str(ev.node_run_id) if ev.node_run_id else None,
        "payload": ev.payload_json,
    }


class EventRecorder:
    def __init__(self, session: AsyncSession, bus: EventBus, run_id: uuid.UUID) -> None:
        self.session = session
        self.bus = bus
        self.run_id = run_id
        self._next: int | None = None
        self._pending: list[dict[str, Any]] = []

    async def _sequence(self) -> int:
        if self._next is None:
            current = await self.session.scalar(
                select(func.max(ExecutionEvent.sequence_no)).where(ExecutionEvent.run_id == self.run_id)
            )
            self._next = (current or 0) + 1
        seq = self._next
        self._next += 1
        return seq

    async def add(
        self,
        type_: EventType,
        payload: SafeEventPayload | dict[str, Any] | None = None,
        *,
        node_run_id: uuid.UUID | None = None,
    ) -> ExecutionEvent:
        safe = payload if isinstance(payload, SafeEventPayload) else SafeEventPayload(**(payload or {}))
        ev = ExecutionEvent(
            run_id=self.run_id,
            sequence_no=await self._sequence(),
            type=type_.value,
            node_run_id=node_run_id,
            payload_json=safe.model_dump(exclude_none=True),
            occurred_at=datetime.now(UTC),
        )
        self.session.add(ev)
        await self.session.flush()
        self._pending.append(event_to_wire(ev))
        return ev

    async def commit(self) -> None:
        """Commit the surrounding transaction, then fan out everything recorded since the last commit."""
        await self.session.commit()
        pending, self._pending = self._pending, []
        for wire in pending:
            await self.bus.publish(str(self.run_id), wire)


async def replay(
    session: AsyncSession, run_id: uuid.UUID, *, after: int = 0, limit: int = 5000
) -> list[ExecutionEvent]:
    rows = await session.scalars(
        select(ExecutionEvent)
        .where(ExecutionEvent.run_id == run_id, ExecutionEvent.sequence_no > after)
        .order_by(ExecutionEvent.sequence_no)
        .limit(limit)
    )
    return list(rows.all())
