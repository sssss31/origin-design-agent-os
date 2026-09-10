# ADR 0003 — Event-sourced run execution with SSE replay

**Status:** accepted · **Date:** 2026-09-10

## Context
The UI must show node-by-node status live and reconstruct it after refresh. Workers may
restart mid-run. Clarification pauses a run for an unbounded time.

## Decision
`execution_events(run_id, sequence_no, type, payload)` is the source of truth, written
in the same transaction as the run/node projection update, then published on the
`EventBus` for live subscribers. The SSE endpoint replays rows after `Last-Event-ID`
and then tails the bus. Run/node states follow the transition tables in
`app/domain/run_state.py`.

## Consequences
- Refresh, reconnect and worker restarts are all handled by replay.
- Event payloads go through a whitelist schema; reasoning never enters an event.
- A future DAG scheduler emits the same event types.
