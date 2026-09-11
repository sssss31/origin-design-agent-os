"""Load test: N concurrent runs streaming events over SSE (spec §16 P8, §18 Load).

Usage:
  python scripts/load_test_sse.py --base http://localhost:8000/api/v1 --email admin@origin.local \
      --password 'ChangeMe123!' --conversation <conversation-id> --runs 25 --command /copy

Reports p50/p95 time-to-first-event and time-to-completion. Uses the Echo provider unless the
target agent is configured otherwise; run against staging, never production.
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import time

import httpx


async def one_run(client: httpx.AsyncClient, base: str, headers: dict[str, str], conversation: str, command: str, i: int) -> tuple[float, float, str]:
    t0 = time.perf_counter()
    res = await client.post(f"{base}/conversations/{conversation}/runs", headers=headers, json={"content": f"{command} load test message {i}"})
    res.raise_for_status()
    run_id = res.json()["run_id"]
    first = None
    status = "?"
    async with client.stream("GET", f"{base}/runs/{run_id}/events", headers=headers, timeout=120) as stream:
        async for line in stream.aiter_lines():
            if line.startswith("event: "):
                if first is None:
                    first = time.perf_counter() - t0
                status = line[7:]
                if status in ("run.completed", "run.failed", "run.cancelled"):
                    break
    return first or 0.0, time.perf_counter() - t0, status


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000/api/v1")
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--conversation", required=True)
    ap.add_argument("--runs", type=int, default=20)
    ap.add_argument("--concurrency", type=int, default=10)
    ap.add_argument("--command", default="/copy")
    args = ap.parse_args()
    async with httpx.AsyncClient(timeout=60) as client:
        login = await client.post(f"{args.base}/auth/login", json={"email": args.email, "password": args.password})
        login.raise_for_status()
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        sem = asyncio.Semaphore(args.concurrency)

        async def guarded(i: int) -> tuple[float, float, str]:
            async with sem:
                return await one_run(client, args.base, headers, args.conversation, args.command, i)

        started = time.perf_counter()
        results = await asyncio.gather(*(guarded(i) for i in range(args.runs)), return_exceptions=True)
    ok = [r for r in results if isinstance(r, tuple)]
    errors = [r for r in results if not isinstance(r, tuple)]
    firsts = sorted(r[0] for r in ok)
    totals = sorted(r[1] for r in ok)
    outcomes = {s: sum(1 for r in ok if r[2] == s) for s in {r[2] for r in ok}}

    def pct(values: list[float], p: float) -> float:
        if not values:
            return 0.0
        return values[min(len(values) - 1, int(round(p * (len(values) - 1))))]

    print(f"runs={args.runs} concurrency={args.concurrency} wall={time.perf_counter() - started:.1f}s errors={len(errors)} outcomes={outcomes}")
    print(f"time-to-first-event p50={pct(firsts, 0.5):.3f}s p95={pct(firsts, 0.95):.3f}s")
    print(f"time-to-complete    p50={pct(totals, 0.5):.3f}s p95={pct(totals, 0.95):.3f}s mean={statistics.mean(totals) if totals else 0:.3f}s")
    for e in errors[:5]:
        print("error:", e)


if __name__ == "__main__":
    asyncio.run(main())
