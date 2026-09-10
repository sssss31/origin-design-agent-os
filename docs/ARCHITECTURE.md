# Pipeline Architecture

This document explains how a user message becomes a run, how the run executes, how every
part is swappable, and where to go to change something. It is written for whoever upgrades
the system after V0.

## 1. The request → run → artifact pipeline

```
 Browser (Next.js)                         FastAPI (apps/api)                                  Adapters (swappable)
 ───────────────────                       ──────────────────────────────────────────────      ────────────────────
 Composer  ──POST /messages──▶  1. Persist message
           ──POST /runs────▶    2. RunService.create()     ─▶ workflow_runs(QUEUED)
                                   └─ JobQueue.enqueue(run_id) ──────────────────────────▶  InlineQueue | RedisQueue
                                                                                                │
                                3. RunExecutor.execute(run_id)   (worker)  ◀────────────────────┘
                                   a. Router.resolve      : /command → active agent_version   (DB)
                                   b. ContextManager.build: project summary, assets, messages (DB, EmbeddingProvider?)
                                   c. PromptComposer      : platform → org → agent → skills → project → task → user
                                   d. WorkflowScheduler   : Sequential (V0) | Dag (later)
                                   e. per node: AgentRunner.run(agent, input, tools)  ─────▶  EchoRunner | OpenAIAgentsRunner
                                        └─ ToolExecutor.call(tool, args)   ───────────────▶  internal_function | http_api | mcp | sandbox
                                        └─ ArtifactService.persist(file)   ───────────────▶  ObjectStorage: LocalFS | S3/R2/MinIO
                                   f. EventBus.publish(run_id, event)  ──▶ execution_events (DB, source of truth)
                                                                        └▶ live fan-out: InMemoryBus | RedisPubSub
 ExecutionPanel ◀──GET /runs/{id}/events (SSE)── replay from DB since Last-Event-ID, then tail EventBus
 ClarificationCard ──POST /runs/{id}/clarification──▶ RunService.resume() → re-enqueue same run_id
```

Key properties:
- **Durable by construction.** Every state change is an `execution_events` row with a
  per-run `sequence_no`. `workflow_runs.status` and `node_runs.status` are projections.
  A refresh replays events; a worker crash re-claims the run from its last event.
- **Sequential now, DAG later.** `workflow_versions.nodes_json` + `edges_json` are stored
  from day one. `SequentialScheduler` ignores edges and walks nodes in order. A
  `DagScheduler` will use the edges and can run independent nodes in parallel. The run
  tables do not change.
- **Nothing hardcoded.** Agent instructions, model, provider, skills, tools, handoffs and
  workflow definitions come from versioned DB rows resolved *at run time*. Seed scripts only
  insert rows the admin can later edit.

## 2. Layers inside `apps/api/app`

| Layer | Folder | Rule |
|-------|--------|------|
| Domain | `domain/` | Pure Python: state machines, enums, slash parser, event types. No I/O, no SQLAlchemy. 100% unit-testable. |
| Ports | `ports/` | `typing.Protocol` interfaces for every external capability. Services depend only on these. |
| Adapters | `adapters/` | Concrete implementations of ports. Chosen by settings in `adapters/registry.py`. |
| Models | `models/` | SQLAlchemy tables. One module per bounded context. |
| Services | `services/` | Use-cases. Take an `AuthContext` + session + ports. Emit audit entries. |
| API | `api/v1/` | Thin routers: parse → authorize (dependencies) → call service → serialize. |
| Workers | `workers/` | Queue consumers that call services (`RunExecutor`). |

Dependency direction: `api → services → (ports, models, domain)`; `adapters → ports`.
Nothing imports from `api/`.

## 3. Ports (extension points) and how to swap them

| Port (`app/ports/…`) | V0 adapters | Setting | Add a new one by |
|------|-------------|---------|------------------|
| `ObjectStorage` | `LocalFSStorage`, `S3Storage` (S3/R2/MinIO) | `STORAGE_BACKEND=local\|s3` | implement `put/get/delete/presign_download/presign_upload/exists`, register in `adapters/registry.py` |
| `SecretStore` | `FernetSecretStore` (encrypted in DB), `EnvSecretStore` | `SECRET_BACKEND=fernet\|env` | implement `store/retrieve/rotate/delete/fingerprint`; a KMS adapter returns a reference not the value |
| `JobQueue` | `InlineQueue` (runs in-process background task), `RedisQueue` | `QUEUE_BACKEND=inline\|redis` | implement `enqueue/claim/ack/nack`; workers stay unchanged |
| `EventBus` | `InMemoryEventBus`, `RedisEventBus` | `EVENT_BUS_BACKEND=memory\|redis` | implement `publish/subscribe(run_id)`; persistence is done by `EventService` before publish, so the bus is live-only |
| `AgentRunner` | `EchoRunner` (tests/dev), `OpenAIAgentsRunner` (Phase 4) | `ai_providers.type` per provider row | implement `run(RuntimeAgent, RunInput) -> RunOutcome`; register the provider type |
| `ToolExecutor` | `InternalFunctionExecutor`, later `HttpApiExecutor`, `McpExecutor`, `SandboxExecutor` | `tools.executor_type` per tool row | implement `execute(ToolCall) -> ToolResult` with schema validation and redaction |
| `EmbeddingProvider` | `NullEmbeddings` (recency/keyword only), `OpenAIEmbeddings` | `EMBEDDINGS_BACKEND` | requires pgvector for storage; otherwise retrieval falls back |
| `WorkflowScheduler` | `SequentialScheduler` | `WORKFLOW_SCHEDULER=sequential` | `DagScheduler` reads `edges_json` |

All ports are `Protocol`s, so an adapter does not need to subclass anything; it only needs
the methods. `adapters/registry.py` is the single place that maps a setting to a class.

## 4. Data model overview (spec §10)

Phase 1 creates identity, workspace and governance. Later phases add the other groups
with their own migrations; no table is ever modified destructively without a migration.

```
users ─┬─ organization_members ─── organizations ─┬─ workspaces ─┬─ workspace_members
       └─ refresh_tokens                           │              └─ projects ─── project_rules
                                                   └─ audit_logs
```

Conventions (`app/db/base.py`): UUID primary keys, `created_at/updated_at` in UTC,
`created_by/updated_by` on admin-editable entities, soft-delete via `status`/`archived_at`
not row deletion, explicit constraint naming so Alembic autogenerate is stable.

Tenancy rule: every table that stores user data has `organization_id` (directly or via a
one-hop parent). Every service method receives `AuthContext(user_id, organization_id, role)`
and every query filters on it. Router dependencies (`core/authz.py`) resolve
workspace/project access before the handler runs.

## 5. Security boundaries

- Secrets: stored only via `SecretStore`. API responses expose `has_secret` and a
  fingerprint. Logging pipeline has a redaction processor keyed on field names
  (`api_key`, `authorization`, `secret`, `token`, `password`) and on value patterns
  (`sk-…`).
- Auth: access JWT (15 min) + rotating refresh token (30 days, hashed at rest, revocable).
  Passwords use Argon2id.
- CORS: explicit allowlist from settings. Production refuses `*`.
- Uploads: MIME + size + filename validation; assets are `pending` until the object
  exists in storage; downloads via short-lived signed URLs; SVG/HTML never rendered
  inline on the app origin.
- Events: payloads are built through `SafeEventPayload` which whitelists fields. Model
  reasoning is never mapped to an event.

## 6. Configuration profiles

`APP_ENV=development|test|staging|production`. In `staging`/`production` the settings
validator refuses default `JWT_SECRET`/`ENCRYPTION_KEY`, `local` storage, `inline`
queue and wildcard CORS. Everything is an environment variable; see `.env.example`.
Admin-tunable runtime configuration (agents, skills, providers, tools, workflows) lives
in the database and takes effect on the next request.

## 7. How to change things (upgrade guide)

| I want to… | Go to |
|------------|-------|
| add an API endpoint | `api/v1/<domain>.py` (router) + `services/<domain>.py` (logic) + `schemas/<domain>.py` |
| add a table | `models/<domain>.py` then `make migrate m="…"`; never edit an applied migration |
| add a run event type | `domain/events.py` + `packages/shared-schemas/execution-event.schema.json` + web `types/events.ts` |
| change run/node states | `domain/run_state.py` (transition table) and its tests |
| plug in another LLM provider | `adapters/runners/<name>.py` implementing `AgentRunner`; add the provider `type` to `ProviderType` |
| add a built-in tool | `tools/<name>.py` with a `ToolSpec`; register in `tools/registry.py`; it becomes an editable `tools` row on seed |
| move to a DAG engine | new `adapters/scheduler/dag.py`; set `WORKFLOW_SCHEDULER=dag` |
| swap MinIO for S3/R2 | set `STORAGE_BACKEND=s3` and the `OBJECT_STORAGE_*` variables |
| change the UI theme/components | `apps/web/src/app/globals.css` (tokens) and `src/components/ui/*` |
