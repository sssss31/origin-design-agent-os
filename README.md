# Origin Design Agent OS

One chat. Multiple specialized design agents. Shared workspace. Observable workflows.

A self-contained monorepo implementing the
*Origin Design Agent OS — V0 → Production Implementation Specification*.

| Part | Path | Stack |
|------|------|-------|
| API | `apps/api` | FastAPI · SQLAlchemy 2 (async, psycopg 3) · Alembic · PostgreSQL |
| Web | `apps/web` | Next.js 16 · TypeScript · Tailwind 4 |
| Shared schemas | `packages/shared-schemas` | JSON Schema generated from the API domain |
| Infra | `infra/` | docker-compose (Postgres+pgvector, Redis, MinIO), Dockerfiles |
| Docs | `docs/` | `PLAN.md`, `ARCHITECTURE.md`, ADRs, runbook, phase reports |

## Quick start (local, no Docker)

Requirements: Python 3.12+, Node 20+, a PostgreSQL 15+ database.

```bash
cp .env.example .env                 # set DATABASE_URL to your Postgres
make setup                           # API venv + web npm install
make migrate                         # alembic upgrade head
make bootstrap-admin                 # first admin + organization (interactive)
make api                             # http://localhost:8000  (docs at /docs)
make web                             # http://localhost:3000  (proxies /api/v1 to the API)
```

In development the first admin can also be created from `.env`
(`BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD`); staging/production refuse those
variables and require the CLI.

## Full stack with Docker

```bash
cp .env.example .env
make compose-up
```

Starts Postgres (pgvector image), Redis, MinIO, the API (migrations run on start), a queue
worker and the web app. Adapters switch automatically to S3 storage, Redis queue and
Redis event bus (see `infra/docker-compose.yml`).

## Quality gates

```bash
make lint        # ruff + eslint
make typecheck   # mypy + tsc
make test        # pytest: unit + API + migrations (needs TEST_DATABASE_URL or local Postgres)
cd apps/web && npm test && npm run build
```

## Where things are

- Changing behaviour without a redeploy: agents, skills, providers, tools, workflows are
  database rows (Phase 2+). Environment variables are only for infrastructure.
- Swapping infrastructure (storage, queue, events, LLM runtime, scheduler): one adapter
  under `apps/api/app/adapters/` and one line in `adapters/registry.py`. See
  `docs/ARCHITECTURE.md` §3 and §7.
- Build order and spec coverage: `docs/PLAN.md`. Phase reports: `docs/reports/`.
