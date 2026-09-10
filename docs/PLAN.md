# Origin Design Agent OS — Implementation Plan (verified against the spec)

Source of truth: `Origin_Design_Agent_OS_Claude_Execution_Spec (1).md` (10 Sep 2026).
This plan turns the spec into an ordered, testable build. Every phase has a scope, the
modules it touches, its acceptance test, and the spec sections it satisfies. The
"Verification" section at the end maps every Definition-of-Done row and every Final
Acceptance Checklist item to a phase and a module, so nothing in the spec is silently dropped.

## 0. Decisions made before building (assumptions the spec left open)

| # | Decision | Why |
|---|----------|-----|
| A1 | Self-contained monorepo in its own repository (`origin-design-agent-os`). Initially developed inside the PathSense repository under `origin-design-agent-os/` and extracted unchanged. | One product per repository; the layout in §1 is the repository root. |
| A2 | Python 3.14, FastAPI, SQLAlchemy 2 async on `postgresql+psycopg` (psycopg 3). | Matches the spec's `DATABASE_URL=postgresql+psycopg://…` and has wheels for 3.14; asyncpg does not. |
| A3 | Hexagonal layout: `ports/` (Protocols) + `adapters/` (implementations) + `services/` (use-cases) + `domain/` (pure state machines/enums). Every external dependency (storage, secrets, queue, events, LLM runtime, tools) is behind a port and selected by configuration. | This is what makes the pipeline upgradeable: swapping MinIO→S3, inline→Redis queue, OpenAI→another provider, or adding a DAG engine touches one adapter and zero call sites. |
| A4 | Local-first defaults: filesystem object storage, inline job queue, in-process event bus, Fernet-encrypted secrets in DB. Production profiles switch to S3/R2, Redis queue + Redis pub/sub, and a KMS/secret-manager reference. | The spec asks for S3-compatible storage and Redis; the machine has neither Docker nor Redis. Adapters keep dev and prod on the same code path. |
| A5 | pgvector is optional (spec §2). The knowledge/embedding tables are created only when the `vector` extension exists; retrieval degrades to recency + keyword. | The available Postgres 17 has no pgvector. |
| A6 | Auth = short-lived JWT access token + rotating refresh token persisted (hashed) in DB. Roles: `admin`, `member`, `viewer` at organization level, and per-workspace membership roles. | Spec §16 Phase 1 and §17 (server-side authorization, refresh endpoint). Persisted refresh tokens allow revocation. |
| A7 | Run execution is event-sourced: `execution_events(run_id, sequence_no)` is the source of truth; run/node rows are projections. SSE replays from the DB, then tails live events. | Spec §14: "UI derives node status from persisted events, so refreshing the page reconstructs the same timeline." |
| A8 | Workflow definitions store `nodes_json` + `edges_json` from day one; V0 executes them sequentially with a `SequentialScheduler`. A `DagScheduler` is a later drop-in behind the same `WorkflowScheduler` port. | Spec §9/§22 rule 6. |
| A9 | Secrets never cross the API boundary outward: provider responses carry `has_secret`, `secret_fingerprint` (last 4 chars hash) and `last_tested_at` only. Logging uses a redaction processor. | Spec §6, §17. |

## 1. Repository layout (spec §15, refined)

```
origin-design-agent-os/
├── apps/
│   ├── api/                      # FastAPI service
│   │   ├── app/
│   │   │   ├── main.py           # app factory, middleware, routers
│   │   │   ├── cli.py            # bootstrap-admin, seed, migrate helpers
│   │   │   ├── core/             # config, logging, security, errors, request context
│   │   │   ├── db/               # engine/session, base, naming conventions, mixins
│   │   │   ├── models/           # SQLAlchemy models, one module per domain
│   │   │   ├── schemas/          # Pydantic I/O models, one module per domain
│   │   │   ├── domain/           # pure logic: run/node state machines, event types, slash parser
│   │   │   ├── ports/            # Protocols: ObjectStorage, SecretStore, JobQueue, EventBus, AgentRunner, ToolExecutor, EmbeddingProvider, WorkflowScheduler
│   │   │   ├── adapters/         # implementations of ports (local_fs, s3, fernet, env, inline, redis, echo runner, openai runner…)
│   │   │   ├── services/         # use-cases: auth, workspaces, projects, audit, agents, skills, providers, context, workflows, artifacts
│   │   │   ├── api/v1/           # routers only; no business logic
│   │   │   ├── tools/            # built-in tool implementations (image, file, svg, pdf…)
│   │   │   └── workers/          # queue consumers (run executor)
│   │   ├── alembic/              # migrations
│   │   ├── tests/                # unit/, api/, db/, workflow/
│   │   └── pyproject.toml
│   └── web/                      # Next.js 16 + TypeScript + Tailwind
│       ├── src/app/              # routes from spec §14
│       ├── src/components/
│       ├── src/lib/api/          # typed client, auth, SSE
│       └── src/types/
├── packages/
│   └── shared-schemas/           # JSON Schemas shared by api + web (events, artifacts, tools)
├── infra/
│   ├── docker-compose.yml        # postgres(pgvector) + redis + minio + api + web
│   ├── deploy/                   # Dockerfiles, entrypoints
│   └── migrations/               # (pointer) migrations live in apps/api/alembic
├── docs/                         # PLAN, ARCHITECTURE, ADRs, runbooks, phase reports
├── Makefile
└── .env.example
```

## 2. Phases

Each phase ends with: formatters + type check + migrations from empty DB + tests, then a
completion report using the spec §23 template (saved under `docs/reports/`).

### Phase 1 — Foundation (COMPLETE — see `docs/reports/phase-1.md`)
Scope (spec §16 P1, §2, §6 env, §10 identity/workspace/governance, §17):
- Monorepo, `apps/api` (FastAPI) and `apps/web` (Next.js), `infra/docker-compose.yml` with Postgres (pgvector image), Redis, MinIO.
- Settings layer (`core/config.py`) with profiles `development|test|staging|production`, fail-fast validation in production (no default secrets).
- Structured JSON logging with secret redaction, request-id middleware, strict CORS, `/healthz` (liveness) and `/readyz` (DB + storage + queue checks).
- Alembic; migration `0001_identity_workspace_governance`: users, organizations, organization_members, refresh_tokens, workspaces, workspace_members, projects, project_rules, audit_logs.
- Auth: argon2 password hashing, login/refresh/logout, `/me`, roles admin/member/viewer, org + workspace scoped authorization dependencies.
- Workspace/project CRUD with membership enforcement and audit log entries.
- **Pipeline contracts** (ports) + local adapters + domain state machines, so later phases plug in without redesign.
- Web: `/login`, `/app`, `/app/workspaces`, `/app/workspaces/[id]` with typed API client and auth session.
- Tests: unit (config, security, state machines, slash parser, adapters), API (auth, tenant isolation/IDOR, workspace/project flows), DB (migrate from empty, downgrade/upgrade).
- Acceptance: user logs in, creates workspace/project, backend tests pass, migrations run from an empty database.

### Phase 2 — Admin configuration core (COMPLETE — see `docs/reports/phase-2.md`)
Scope (spec §4, §5, §6, §16 P2): tables + services for `ai_providers`, `provider_models`, `secret_refs`, `agents`, `agent_versions`, `agent_skill_bindings`, `agent_tool_bindings`, `agent_handoffs`, `skills`, `skill_versions`, `skill_files`, `tools`, `tool_versions`, `tool_permissions`. Draft/publish/rollback (`active_version_id` atomic switch), provider secret write-only endpoint + `test` (minimal authenticated request), model allowlist, audit on every publish/secret/permission change. Admin UI pages: Agents, Skills, Providers, Tools.
Acceptance: admin adds OpenAI key, creates skill, creates agent, attaches skill/tool, publishes, and the `/command` appears in the composer without redeploy.

### Phase 3 — Chat + files
Scope (§7, §8, §16 P3): `conversations`, `messages`, `message_attachments`, `assets`, `asset_versions`, `artifacts`, `artifact_versions`. Multipart upload → ObjectStorage port (MIME/size/filename validation, no Asset marked ready until upload completes), short-lived signed download URLs, sidebar/new chat/rename/archive/search, composer, artifact preview cards.
Acceptance: chat survives restart; uploaded file visible and downloadable only with authorization.

### Phase 4 — Router + Context + single-agent runtime
Scope (§3 slash commands, §5 prompt composition, §7 context package, §12): slash parser (domain, already in P1), command resolver against active agents, `AgentFactory` from DB version, `PromptComposer` (platform rules → org rules → agent instructions → skills by priority → workspace/project rules → context summary → user request), `ContextManager` (project summary, selected assets, recent + relevant messages), OpenAI Agents SDK adapter behind `AgentRunner` port, `EchoRunner` for tests.
Acceptance: `/copy` runs end-to-end from UI with DB-configured prompt and model.

### Phase 5 — Workflow runs + live events
Scope (§9, §11 runs API, §14 execution panel): `workflow_definitions`, `workflow_versions`, `workflow_runs`, `node_runs`, `execution_events`; run API, SSE stream with replay-from-sequence + live tail (`Last-Event-ID`), cancellation, retry of safe nodes, clarification `WAITING_FOR_USER` pause/resume with persisted resume state, worker with idempotent claim (`FOR UPDATE SKIP LOCKED`).
Acceptance: user sees Parse → Context → Agent → Save Result live and can refresh without losing state.

### Phase 6 — Eight design agents
Scope (§13, §21): seed script for the eight agents + eight skills as versioned records (idempotent, editable afterwards from admin UI), built-in tools (image generation/analysis, file inspection, SVG/PDF processors) registered as `tools` rows with `executor_type=internal_function`, Manager sequential delegation with handoff permissions.
Acceptance: all eight commands resolve to the configured agents.

### Phase 7 — Design workflow hardening
Scope (§8 version flow, §16 P7): artifact lineage (`parent_artifact_id`), approval/final states, structured QC report with severity and pass/fail, revision loop limits, export metadata validation.
Acceptance: master → resize → QC → export completes and is auditable.

### Phase 8 — Security, QA, deployment
Scope (§16 P8, §17, §18, §19): rate limits + org quotas, trace sensitivity off by default, full audit coverage, E2E tests, backup policy docs, staging deploy, load test on concurrent SSE runs, rollback runbook.

## 3. Verification — spec coverage matrix

### Definition of done (spec §0)
| Area | Requirement | Phase | Module(s) |
|------|-------------|-------|-----------|
| Single chat | run /master, /resize, /editable, /qc … from one conversation | 4, 6 | `domain/slash.py`, `services/routing`, `services/agents` |
| Admin | create/edit/disable agents, skills, providers, tools, handoffs from UI | 2 | `models/agents.py`, `services/agents`, `api/v1/admin/*`, web `/admin/*` |
| Context | workspace/project context, files, messages, instructions/skills | 4 | `services/context`, `services/prompt_composer` |
| Clarification | pause run, ask, resume | 5 | `domain/run_state.py` (P1), `services/workflows/clarification` |
| Execution | node-by-node SSE | 5 | `ports/events.py` (P1), `adapters/events/*`, `api/v1/runs.py` |
| Persistence | chats, files, artifacts, runs, versions, configs survive restart | 1–5 | Postgres models + Alembic |
| Security | secrets server-side encrypted, never in browser | 1 (port+adapter), 2 (usage) | `ports/secrets.py`, `adapters/secrets/*`, `core/logging.py` redaction |
| Audit | admin changes and executions auditable | 1 (table+service), 2+ (coverage) | `models/governance.py`, `services/audit.py` |

### Final acceptance checklist (spec §25)
| Item | Phase | Evidence |
|------|-------|----------|
| One chat invokes all enabled agents via slash | 4/6 | E2E test `tests/e2e/test_slash_agents.py` |
| No code change for prompt/model/skill/tool/handoff | 2 | Everything read from `agent_versions` at run time; admin API tests |
| Secure add/test/rotate provider credentials | 2 | write-only secret endpoint; test returns only status |
| Publish/version/rollback skills and agents | 2 | `active_version_id` switch tests |
| Selective, consistent context injection | 4 | `PromptComposer` deterministic unit tests |
| Resumable clarification | 5 | workflow tests: pause → reply → resume same run |
| Live events persist across refresh | 5 | SSE replay test with `Last-Event-ID` |
| Chats persistent + searchable | 3 | `messages` index + search endpoint |
| Generated files are versioned artifacts with lineage | 3/7 | `artifact_versions`, `parent_artifact_id` |
| QC structured pass/fail | 7 | `qc_report` output schema |
| Manager sequential delegation | 6 | `SequentialScheduler` + handoff permission tests |
| Secrets never sent to frontend | 1/2 | schema tests asserting no `secret` fields in responses |
| Tenant authorization server-side | 1 | IDOR tests in `tests/api/test_tenancy.py` |
| Audit logs for sensitive admin changes | 1/2 | `audit_logs` + service tests |
| Core API/workflow/E2E pass in staging | 8 | CI pipeline |

### Rules from spec §0 and §22 checked against the design
- Agents/skills/providers/prompts/routing/models/handoffs are DB entities → Phase 2 tables; nothing hardcoded (seed script only inserts editable rows).
- No secrets in frontend/repo/logs/prompts/DB plaintext → env or Fernet-encrypted `secret_refs`, redaction logger, `.env.example` has placeholders only.
- No chain-of-thought in UI → event payloads are built from a `SafeEventPayload` schema; reasoning fields are never mapped.
- Sequential first, DAG-ready → `edges_json` stored, `WorkflowScheduler` port.
- Every generated file = versioned artifact with lineage → `artifact_versions` with `run_id`, `node_run_id`, `produced_by_agent_version_id`.
- Admin changes effective without redeploy → config read per request from DB; no in-process caches without invalidation.

## 4. Risks and mitigations
| Risk | Mitigation |
|------|------------|
| OpenAI Agents SDK API drift | Isolated in `adapters/runners/openai_agents.py` behind `AgentRunner`; `EchoRunner` keeps tests independent. |
| Long image jobs block API | Queue port; inline in dev, Redis worker in prod; runs are durable so a worker restart re-claims work. |
| SSE behind proxies/CDNs | Heartbeat comments every 15s, `Last-Event-ID` replay, no buffering headers. |
| Multi-tenant data leaks | Every service method takes an `AuthContext`; router-level dependencies enforce org/workspace scope; IDOR tests. |
| Python 3.14 ecosystem | All pinned deps verified to have 3.14 wheels (see `docs/reports/phase-1.md`). |
