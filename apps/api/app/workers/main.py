"""Queue worker process (used when QUEUE_BACKEND=redis).

Run with `python -m app.workers.main`. Phase 5 registers the run executor handler here.
"""

from __future__ import annotations

import asyncio
import signal

from app.adapters.registry import Adapters, build_adapters
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.session import create_engine, create_session_factory

log = get_logger("worker")


def register_handlers(adapters: Adapters) -> None:
    """Phase 5: adapters.queue.register("run.execute", RunExecutor(...).handle)"""


async def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    engine = create_engine(settings)
    adapters = build_adapters(settings, create_session_factory(engine))
    register_handlers(adapters)
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
