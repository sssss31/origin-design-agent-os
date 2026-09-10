PHASE: 1 / Foundation
STATUS: COMPLETE

Implemented
- Monorepo `origin-design-agent-os/` with `apps/api` (FastAPI, Python 3.14), `apps/web` (Next.js 16), `packages/shared-schemas`, `infra/`, `docs/`.
- Settings layer with `development|test|staging|production` profiles; production-like profiles refuse default secrets, wildcard CORS, local storage, inline queue and env-based admin bootstrap.
- Structured JSON/console logging with secret redaction (by key and by value pattern), request-id middleware (`X-Request-Id` in and out), strict CORS, uniform error envelope.
- `/healthz` (liveness) and `/readyz` (database + storage + secrets + queue + event bus) at the root and under `/api/v1`.
- Alembic migration `0001_identity_workspace_governance`: users, organizations, organization_members, refresh_tokens, workspaces, workspace_members, projects, project_rules, audit_logs, secret_refs.
- Auth: Argon2id passwords, JWT access token (15 min) + rotating refresh token stored hashed; reuse of a rotated token revokes the whole family; logout; `/me` with memberships and capabilities.
- Roles admin/member/viewer at organization level; workspace membership roles; org admins see every workspace; org viewers are capped at viewer; objects outside the tenant return 404.
- Workspace and project CRUD, members, project rules, workspace rules text, project summary; every mutation writes an audit row with before/after, actor, request id and IP.
- Pipeline architecture: ports (`ObjectStorage`, `SecretStore`, `JobQueue`, `EventBus`, `AgentRunner`, `ToolExecutor`, `EmbeddingProvider`, `WorkflowScheduler`) with adapters (local FS + S3, Fernet + env, inline + Redis, memory + Redis, Echo runner, internal-function tool executor with JSON-schema validation and redaction, sequential + DAG schedulers) and a single registry mapping settings to adapters.
- Pure domain modules: run/node state machines with transition tables, execution event vocabulary with a whitelisted `SafeEventPayload` (rejects unknown fields such as reasoning), slash-command parser, role ranking, slugs.
- CLI: `check-config`, `migrate`, `bootstrap-admin`, `generate-keys`. Worker entrypoint for the Redis queue.
- Web: `/login`, `/app/workspaces`, `/app/workspaces/[id]` (projects, rules, members), `/app/projects/[id]` (summary, rules, chat placeholder), `/admin` placeholder gated by capability; typed API client with single-flight token refresh; dev proxy for `/api/v1`.
- Infra: docker-compose (Postgres pgvector, Redis, MinIO, api, worker, web), Dockerfiles with non-root users and migration entrypoint, Makefile, `.env.example`, GitHub Actions workflow.

Files created/changed
- Entire repository — new monorepo (see `docs/PLAN.md` §1 for the layout).
- `.github/workflows/ci.yml` — CI for API (ruff, mypy, pytest against Postgres) and web (eslint, tsc, vitest, build).

Database migrations
- revision 0001 `identity workspace governance` (upgrade + downgrade verified by tests).

API routes added
- GET /healthz, GET /readyz (root and /api/v1)
- POST /api/v1/auth/login, POST /api/v1/auth/refresh, POST /api/v1/auth/logout
- GET /api/v1/me
- GET/POST /api/v1/workspaces, GET/PATCH /api/v1/workspaces/{id}, GET/POST /api/v1/workspaces/{id}/members, GET/POST /api/v1/workspaces/{id}/projects
- GET/PATCH /api/v1/projects/{id}, GET/POST /api/v1/projects/{id}/rules, PATCH /api/v1/projects/{id}/rules/{rule_id}
- GET /api/v1/files/{key} (signed download for the local storage adapter only)

Tests
- `cd apps/api && .venv/bin/python -m pytest -q` — result: 63 passed, 0 failed (unit 40, API 17, DB 1; API/DB tests run the real migrations from an empty database on Postgres 17).
- `cd apps/api && ruff check . && ruff format --check . && mypy app` — clean (79 files).
- `cd apps/web && npm run lint && npm run typecheck && npm test && npm run build` — clean; vitest 3 passed; production build succeeds (standalone output).

Manual verification
- API on :8010 with `/readyz` reporting every check true; admin bootstrapped from env in development.
- Browser: login as the bootstrapped admin → create workspace "Brand Studio" → save workspace rules → create project "Autumn Campaign" → save project summary → add project rule. All requests returned 2xx through the Next.js proxy; rows and six audit entries (user.bootstrapped, workspace.created, project.created, workspace.updated, project.updated, project_rule.created) present in Postgres.

Security checks
- Secrets: no plaintext secret column; `secret_refs` stores Fernet ciphertext + fingerprint; `.env.example` has placeholders only; logs redact `api_key`, `authorization`, `password`, `token`, `sk-…`, bearer and JWT-looking values (unit-tested).
- Auth: same 401 for unknown email and wrong password; tampered/expired tokens rejected; refresh-token reuse revokes the family (API-tested).
- Tenancy: cross-organization access to workspaces/projects/rules returns 404; cross-org `X-Organization-Id` returns 403; viewer cannot create (API-tested).
- Files: signed URLs are HMAC-signed and expire; downloads are served with `nosniff` and a sandboxed CSP so uploaded SVG/HTML is never rendered on the app origin; path traversal in storage keys rejected (unit-tested).
- Production profile refuses insecure configuration at startup (unit-tested).

Assumptions / limitations
- Developed inside the PathSense repository first and extracted unchanged into this repository.
- Python 3.14 with psycopg 3 (asyncpg has no 3.14 wheels). UUIDv7 primary keys when the interpreter provides `uuid.uuid7`, otherwise UUIDv4.
- No Docker on the development machine: local adapters (filesystem storage, inline queue, in-memory bus) are the development defaults; the compose stack and production profile use S3/Redis. The Redis and S3 adapters are implemented but were not exercised against live services here.
- pgvector is optional; the local Postgres has no `vector` extension, so semantic memory stays a Phase 4 opt-in.
- Email validation is syntactic only (reserved domains such as `.local` are accepted for internal deployments).
- Browser session keeps the access token in memory and the rotating refresh token in localStorage; moving the refresh token to an httpOnly cookie with CSRF protection is scheduled for Phase 8.
- The workspaces list is requested more than once on first render (sidebar + page + React strict mode); harmless, to be deduplicated when a query cache is introduced with the chat UI.

Next phase prerequisites
- Phase 2 tables: ai_providers, provider_models, agents, agent_versions, agent_skill_bindings, agent_tool_bindings, agent_handoffs, skills, skill_versions, skill_files, tools, tool_versions, tool_permissions (all with `created_by/updated_by` via `AuditedMixin`).
- `SecretStore` is ready for provider secrets; `build_runners()` in `adapters/registry.py` is where the OpenAI runner registers under provider type `openai`.
- `app/tools/registry.py` is ready for built-in tools to be seeded as editable rows.
