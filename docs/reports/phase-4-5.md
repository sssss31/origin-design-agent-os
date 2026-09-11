PHASE: 4 + 5 / Router, context, agent runtime, workflow runs, live events
STATUS: COMPLETE

Implemented
- Router (`services/router.py`): explicit `/command` → active agent (recoverable `agent_unavailable` when disabled meanwhile), no command or `/auto` → Manager agent (`no_manager` otherwise), `preferred_agent_id` override.
- ContextManager (`services/context.py`): project summary, brand configuration marker, selected assets (ids + dimensions), selected or latest approved artifacts, recent turns, keyword-relevant older turns (semantic memory hook when an EmbeddingProvider is configured). Files are referenced, never pasted.
- AgentRunner adapters: `EchoRunner` (offline) and `OpenAIAgentsRunner` (OpenAI Agents SDK, Responses API): bound tools become FunctionTools delegated to our invoker; `ask_user` tool pauses for clarification with resumable SDK input; per-run credentials; usage captured; sensitive tracing off by default.
- Tables (migration 0004): workflow_definitions, workflow_versions (nodes_json/edges_json), workflow_runs, node_runs, execution_events (`UNIQUE(run_id, sequence_no)`), api_usage, error_events.
- RunService: create (route → plan Parse → Context → Agent → Save → enqueue), clarification answer (same run resumes; reply stored as a message), cancel (immediate for queued/waiting, cooperative for running), retry of retryable failures, per-organization run quota.
- RunExecutor (worker): claims runs with `FOR UPDATE SKIP LOCKED`; every state change persisted with its event then published; tool invoker enforces agent bindings, role/workspace permissions and per-run call limits, emits tool.started/completed and persists produced files as artifacts with lineage; clarification → `WAITING_FOR_USER`; failures recorded in error_events with retryable flag; heartbeat for stale-run recovery; startup recovery re-enqueues queued runs and fails stale ones.
- SSE `GET /runs/{id}/events`: replay after `Last-Event-ID`/`after`, then live tail with heartbeats and gap-fill from the database; `GET /runs/{id}/events/history` JSON replay.
- Web: fetch-based SSE client (Authorization header, CRLF-safe framing, resume by sequence), pure `deriveTimeline` projection (unit-tested), ExecutionPanel (nodes, tools, context sources, durations, artifacts, trace drawer, clarification card, cancel/retry), composer slash autocomplete from `GET /agents/commands`, run badges on messages.

Tests
- `tests/api/test_runs.py` — 4 tests: end-to-end slash run with durable events + SSE replay + Last-Event-ID; routing errors and permissions; clarification pause/resume, cancel, provider failure + retry; manager delegation + built-in tools + artifacts + QC + export validation.
- `tests/unit/test_run_state.py`, `test_events.py` (Phase 1) cover the state machines and the payload whitelist.
- Web: `timeline.test.ts` (projection), `sse-parse.test.ts` (CRLF/LF framing).

Manual verification (browser)
- `/auto resize the approved poster to 4:5, run qc on it and export the final` with an attached asset → Manager delegated to Resize → QC → Export; panel showed node timeline with durations and context sources; assistant reply grouped per agent.
- `/resize the poster for instagram ?clarify` → run paused with "Which target sizes do you need?" in the panel; replying "4:5 and 9:16" resumed the same run to SUCCEEDED; events: …clarification.requested, clarification.received, …run.completed.

Assumptions / limitations
- The OpenAI runner is implemented against the current SDK API but was not exercised against the live API in this environment (no key); the Echo provider covers the pipeline in CI.
- Next.js compression is disabled (`compress: false`) because gzip buffering breaks SSE through the dev/standalone proxy; compress at the edge.
- Manager planning falls back to a deterministic keyword plan when the model returns no JSON plan (always the case with Echo).
