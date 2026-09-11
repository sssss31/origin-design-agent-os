"""Startup recovery (spec §19 'Worker restart'): re-enqueue queued runs and fail stale ones."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.registry import Adapters
from app.core.config import Settings
from app.core.logging import get_logger
from app.domain.events import EventType, SafeEventPayload
from app.domain.run_state import NodeState, RunState
from app.models.workflows import WorkflowRun
from app.ports.queue import Job
from app.services.events import EventRecorder

log = get_logger("recovery")


async def recover_runs(
    session_factory: async_sessionmaker[AsyncSession], adapters: Adapters, settings: Settings
) -> dict[str, int]:
    stats = {"requeued": 0, "failed_stale": 0}
    try:
        async with session_factory() as session:
            queued = (
                await session.scalars(select(WorkflowRun.id).where(WorkflowRun.status == RunState.QUEUED))
            ).all()
            for run_id in queued:
                await adapters.queue.enqueue(
                    Job(
                        type="run.execute",
                        payload={"run_id": str(run_id)},
                        idempotency_key=f"recover:{run_id}",
                    )
                )
                stats["requeued"] += 1
            cutoff = datetime.now(UTC) - timedelta(seconds=settings.stale_run_seconds)
            stale = (
                await session.scalars(
                    select(WorkflowRun).where(
                        WorkflowRun.status == RunState.RUNNING, WorkflowRun.heartbeat_at < cutoff
                    )
                )
            ).all()
            for run in stale:
                await session.refresh(run, attribute_names=["nodes"])
                for node in run.nodes:
                    if node.status == NodeState.RUNNING:
                        node.status = NodeState.FAILED
                        node.error_json = {
                            "code": "worker_restart",
                            "message": "the worker stopped while this step was running",
                            "retryable": True,
                        }
                run.status = RunState.FAILED
                run.error_json = {
                    "code": "worker_restart",
                    "message": "recovered after a worker restart; retry the run",
                    "retryable": True,
                }
                run.finished_at = datetime.now(UTC)
                recorder = EventRecorder(session, adapters.events, run.id)
                await recorder.add(
                    EventType.RUN_FAILED,
                    SafeEventPayload(
                        run_status=run.status,
                        error_code="worker_restart",
                        error_message=run.error_json["message"],
                        retryable=True,
                    ),
                )
                await recorder.commit()
                stats["failed_stale"] += 1
    except Exception as exc:  # tables may not exist yet on a fresh database
        log.warning("recovery_skipped", reason=f"{type(exc).__name__}: {str(exc)[:160]}")
        return stats
    if stats["requeued"] or stats["failed_stale"]:
        log.info("recovery_done", **stats)
    return stats
