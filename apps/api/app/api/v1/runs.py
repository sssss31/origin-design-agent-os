"""Run API + Server-Sent Events (spec §11, §14)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from collections.abc import AsyncIterator
from contextlib import aclosing

from fastapi import APIRouter, Header, Query, Request, status
from sse_starlette.sse import EventSourceResponse

from app.core.authz import DB, Auth, Config
from app.core.deps import AdaptersDep
from app.core.logging import get_logger
from app.domain.run_state import TERMINAL_RUN_STATES, RunState
from app.models.workflows import WorkflowRun
from app.schemas.common import from_orm
from app.schemas.runs import ClarificationAnswer, EventOut, NodeRunOut, RunCreate, RunCreated, RunOut
from app.services.events import TERMINAL_EVENTS, event_to_wire, replay
from app.services.runs import RunService

router = APIRouter(tags=["runs"])
log = get_logger("sse")
HEARTBEAT_SECONDS = 15


def _run_out(run: WorkflowRun, svc: RunService) -> RunOut:
    return from_orm(
        RunOut,
        run,
        nodes=[from_orm(NodeRunOut, n) for n in sorted(run.nodes, key=lambda n: n.index)],
        event_stream_url=svc.stream_url(run.id),
    )


@router.post(
    "/conversations/{conversation_id}/runs", response_model=RunCreated, status_code=status.HTTP_202_ACCEPTED
)
async def create_run(
    conversation_id: uuid.UUID,
    body: RunCreate,
    ctx: Auth,
    session: DB,
    adapters: AdaptersDep,
    settings: Config,
) -> RunCreated:
    svc = RunService(session, ctx, adapters, settings)
    run = await svc.create(conversation_id, body)
    return RunCreated(
        run_id=run.id, status=run.status, event_stream_url=svc.stream_url(run.id), message_id=run.message_id
    )


@router.get("/conversations/{conversation_id}/runs", response_model=list[RunOut])
async def list_runs(
    conversation_id: uuid.UUID, ctx: Auth, session: DB, adapters: AdaptersDep, settings: Config
) -> list[RunOut]:
    svc = RunService(session, ctx, adapters, settings)
    return [_run_out(r, svc) for r in await svc.list_for_conversation(conversation_id)]


@router.get("/runs/{run_id}", response_model=RunOut)
async def get_run(
    run_id: uuid.UUID, ctx: Auth, session: DB, adapters: AdaptersDep, settings: Config
) -> RunOut:
    svc = RunService(session, ctx, adapters, settings)
    return _run_out(await svc.get(run_id), svc)


@router.post("/runs/{run_id}/clarification", response_model=RunOut)
async def answer_clarification(
    run_id: uuid.UUID,
    body: ClarificationAnswer,
    ctx: Auth,
    session: DB,
    adapters: AdaptersDep,
    settings: Config,
) -> RunOut:
    svc = RunService(session, ctx, adapters, settings)
    return _run_out(await svc.answer_clarification(run_id, body), svc)


@router.post("/runs/{run_id}/cancel", response_model=RunOut)
async def cancel_run(
    run_id: uuid.UUID, ctx: Auth, session: DB, adapters: AdaptersDep, settings: Config
) -> RunOut:
    svc = RunService(session, ctx, adapters, settings)
    return _run_out(await svc.cancel(run_id), svc)


@router.post("/runs/{run_id}/retry", response_model=RunOut)
async def retry_run(
    run_id: uuid.UUID, ctx: Auth, session: DB, adapters: AdaptersDep, settings: Config
) -> RunOut:
    svc = RunService(session, ctx, adapters, settings)
    return _run_out(await svc.retry(run_id), svc)


@router.get("/runs/{run_id}/events/history", response_model=list[EventOut])
async def event_history(
    run_id: uuid.UUID,
    ctx: Auth,
    session: DB,
    adapters: AdaptersDep,
    settings: Config,
    after: int = Query(default=0, ge=0),
) -> list[EventOut]:
    """Plain JSON replay (same rows the SSE stream sends) for clients that cannot hold a stream."""
    await RunService(session, ctx, adapters, settings).get(run_id)
    return [EventOut(**event_to_wire(e)) for e in await replay(session, run_id, after=after)]


@router.get("/runs/{run_id}/events")
async def event_stream(
    run_id: uuid.UUID,
    request: Request,
    ctx: Auth,
    session: DB,
    adapters: AdaptersDep,
    settings: Config,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    after: int | None = Query(default=None, ge=0),
) -> EventSourceResponse:
    """SSE: replay persisted events after `Last-Event-ID`, then tail live events until the run ends."""
    run = await RunService(session, ctx, adapters, settings).get(run_id)
    start_after = (
        after if after is not None else int(last_event_id) if last_event_id and last_event_id.isdigit() else 0
    )
    session_factory = request.app.state.session_factory
    bus = adapters.events
    # Serverless hosting: nothing runs after a response is sent, so a queued run is executed here,
    # inside the request that streams its events (the queue only recorded the intent).
    worker: asyncio.Task[None] | None = None
    if settings.serverless and run.status == RunState.QUEUED:
        worker = asyncio.create_task(request.app.state.run_executor.execute(run_id))
        request.app.state.background_tasks.add(worker)
        worker.add_done_callback(request.app.state.background_tasks.discard)

    async def settle() -> None:
        if worker is not None and not worker.done():
            with contextlib.suppress(TimeoutError, asyncio.CancelledError):
                await asyncio.wait_for(asyncio.shield(worker), timeout=20)

    async def generator() -> AsyncIterator[dict]:
        last = start_after
        terminal = run.status in TERMINAL_RUN_STATES
        async with aclosing(bus.subscribe(str(run_id))) as live:
            # 1) replay from the database (subscription is already open so nothing is missed in between)
            async with session_factory() as s:
                for ev in await replay(s, run_id, after=last):
                    last = ev.sequence_no
                    yield {"id": str(ev.sequence_no), "event": ev.type, "data": json.dumps(event_to_wire(ev))}
                    if ev.type in TERMINAL_EVENTS:
                        terminal = True
            if terminal:
                await settle()
                return
            # 2) tail live events; heartbeats keep proxies from closing idle streams
            while not await request.is_disconnected():
                try:
                    wire = await asyncio.wait_for(live.__anext__(), timeout=HEARTBEAT_SECONDS)
                except TimeoutError:
                    yield {"comment": "heartbeat"}
                    continue
                except StopAsyncIteration:
                    return
                if wire["sequence_no"] <= last:
                    continue
                if wire["sequence_no"] > last + 1:  # gap: fill from the database
                    async with session_factory() as s:
                        for ev in await replay(s, run_id, after=last):
                            if ev.sequence_no >= wire["sequence_no"]:
                                break
                            last = ev.sequence_no
                            yield {
                                "id": str(ev.sequence_no),
                                "event": ev.type,
                                "data": json.dumps(event_to_wire(ev)),
                            }
                last = wire["sequence_no"]
                yield {"id": str(wire["sequence_no"]), "event": wire["type"], "data": json.dumps(wire)}
                if wire["type"] in TERMINAL_EVENTS:
                    await settle()
                    return
            await settle()

    return EventSourceResponse(generator(), headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
