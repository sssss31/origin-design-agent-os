"""Queue worker process (used when QUEUE_BACKEND=redis).

Run with `python -m app.workers.main`. Phase 5 registers the run executor handler here.
"""

from __future__ import annotations

import asyncio
import signal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.registry import Adapters, build_adapters
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger
from app.db.session import create_engine, create_session_factory

log = get_logger("worker")


def register_handlers(
    adapters: Adapters, session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    from app.workers.run_executor import RunExecutor

    adapters.queue.register("run.execute", RunExecutor(session_factory, adapters, settings).handle)


async def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    adapters = build_adapters(settings, session_factory)
    register_handlers(adapters, session_factory, settings)
    from app.workers.recovery import recover_runs

    await recover_runs(session_factory, adapters, settings)
    run_worker = getattr(adapters.queue, "run_worker", None)
    if run_worker is None:
        log.error(
            "worker_not_needed",
            queue=adapters.queue.name,
            hint="inline queue runs jobs inside the API process",
        )
        return
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    log.info("worker_started", queue=adapters.queue.name)
    try:
        await run_worker(stop=stop)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
