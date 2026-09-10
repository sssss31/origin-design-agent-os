# Runbook

## Environments
| Profile | `APP_ENV` | Storage | Queue | Events | Secrets | Notes |
|---------|-----------|---------|-------|--------|---------|-------|
| local | development | local FS | inline | memory | fernet (ephemeral key if unset) | `/docs` enabled, env bootstrap admin allowed |
| test | test | local FS (tmp) | inline | memory | fernet | schema recreated from migrations per run |
| staging / production | staging / production | s3 | redis | redis | fernet with `ENCRYPTION_KEY` or env | strict validation at startup; `/docs` disabled |

Generate secrets: `python -m app.cli generate-keys`. Rotating `ENCRYPTION_KEY` requires
re-encrypting `secret_refs` (Phase 2 adds `origin-cli rotate-encryption-key`).

## Database
- Apply: `python -m alembic upgrade head` (containers do this in the entrypoint).
- Roll back one revision: `python -m alembic downgrade -1`. Every migration has a tested `downgrade()`.
- Backups: nightly `pg_dump -Fc` + object-storage bucket versioning. Restore = restore dump, then `alembic upgrade head`.
- pgvector is optional. Migrations that need it are guarded and skip when the extension is missing.

## Health
- `GET /healthz` — process is up (no dependencies).
- `GET /readyz` — database + storage + queue + event bus + secret store; returns 503 with the failing check named.

## Logs
Structured JSON in staging/production (`LOG_FORMAT=json`). Every line carries `request_id`;
clients receive it as `X-Request-Id` and in error envelopes. Secrets are redacted by key
name and by value pattern before emission.

## Common operations
| Task | Command |
|------|---------|
| First admin | `python -m app.cli bootstrap-admin --email … --organization …` |
| Validate config for an environment | `APP_ENV=production python -m app.cli check-config` |
| Run worker (redis queue) | `python -m app.workers.main` |
| Regenerate shared schemas | `make export-schemas` |

## Rollback procedure (deploy)
1. Redeploy the previous image tag (API and web are independent).
2. If the release added a migration that the previous code cannot run against, `alembic downgrade <prev>` first. Migrations are written to be backward compatible for one release where possible (add columns nullable, backfill, then constrain in the next release).
3. Confirm `/readyz` on every replica.
