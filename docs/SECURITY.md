# Security review — V0

Scope: the API (`apps/api`), the web app (`apps/web`) and the deployment configuration.
Spec references: §6 (providers/secrets), §17 (security & governance), §18 (security tests),
§19 (error handling).

## Automated checks (run on every CI build)

| Check | Tool | Result at release |
|-------|------|-------------------|
| Python static analysis (medium+ severity) | `bandit -r app -ll` | 0 findings (SVG parsing hardened with `defusedxml`) |
| Python dependency vulnerabilities | `pip-audit -r requirements.lock.txt` | 0 known vulnerabilities |
| JavaScript dependency vulnerabilities | `npm audit` | 0 vulnerabilities |
| Lint / type safety | `ruff`, `mypy --strict-optional`, `eslint`, `tsc` | clean |
| Security test suite | `pytest tests/api tests/e2e` | tenant isolation, IDOR, secret leakage, signed URLs, role enforcement, upload validation |

## Controls checklist (spec §17)

- [x] Provider credentials are server-side only. `POST /admin/providers/{id}/secret` is write-only; responses and audit rows carry a hashed fingerprint, never the value. Tests assert the key string is absent from every response and from `secret_refs.ciphertext`.
- [x] Stored credentials are encrypted (Fernet, `ENCRYPTION_KEY`) or referenced from the environment (`SECRET_BACKEND=env`). A managed secret store is one adapter away.
- [x] Object storage is private; downloads use short-lived signed URLs (HMAC for local storage, presigned for S3/R2/MinIO). Signature tampering is rejected (tested).
- [x] Every API query is organization/workspace scoped through `AuthContext`; objects outside the tenant return 404; cross-org headers return 403 (tested for workspaces, projects, assets, artifacts, runs, admin entities).
- [x] Tools are restricted per agent version (`agent_tool_bindings`) with per-run call limits and role/workspace `tool_permissions` enforced by the executor. An unbound tool call returns `tool_not_allowed`.
- [x] Uploads validate MIME allowlist, size cap, extension/MIME match and sanitise filenames; assets are created only after the object exists in storage.
- [x] Uploaded SVG/HTML is never rendered on the app origin: the local download route sets `Content-Security-Policy: sandbox`, `X-Content-Type-Options: nosniff` and `Content-Disposition: attachment`.
- [x] Auth: Argon2id passwords, 15-minute JWT access tokens, rotating refresh tokens stored hashed; reuse of a rotated refresh token revokes the whole family. Same 401 for unknown email and wrong password.
- [x] CORS is an explicit allowlist; production refuses `*`, default secrets, local storage and the inline queue at startup.
- [x] Full audit trail: provider create/update/secret/test/models, tool create/update/secret/permission, skill and agent create/draft/publish/rollback/bindings/handoffs/test, workspace/project/rule changes, asset uploads, artifact status changes, run create/cancel/retry/clarification.
- [x] Tracing: `OPENAI_AGENTS_TRACE_INCLUDE_SENSITIVE_DATA=false` by default; execution event payloads go through a whitelist schema that rejects reasoning or raw provider payloads.
- [x] Logs redact secret-looking values and sensitive keys before emission.
- [x] Rate limiting per user/IP (`RATE_LIMIT_PER_MINUTE`, Redis-backed when available) and per-organization run quotas (`quota_runs_per_day`).
- [x] Security headers on the web app (`X-Frame-Options: DENY`, `nosniff`, referrer policy); API docs disabled in production.

## Residual risks and follow-ups

| Risk | Mitigation status |
|------|-------------------|
| Refresh token in `localStorage` (XSS exposure) | Access token is memory-only and short-lived; refresh rotation + family revocation limits blast radius. Move refresh to an httpOnly cookie + CSRF token when the app gets a BFF layer. |
| Malware in uploads | MIME/size validation only. Wire a scanner (ClamAV or a cloud scanning API) into `services/uploads.py` for enterprise tenants. |
| OpenAI runner not exercised live in CI | Adapter is isolated behind `AgentRunner`; add a nightly smoke job with a scoped key when a staging project exists. |
| In-memory rate limiter on multi-replica deployments | Set `REDIS_URL`; the limiter switches to shared counters automatically. |
| Long-running image jobs on the API process | Use `QUEUE_BACKEND=redis` with dedicated workers in staging/production (compose does this). |

## Backup policy (spec §16 P8)

- PostgreSQL: nightly `pg_dump -Fc` retained 30 days + WAL archiving/PITR on managed Postgres.
- Object storage: bucket versioning enabled; lifecycle rule keeps non-current versions 90 days.
- Restore drill: restore the dump to a fresh database, run `alembic upgrade head`, point the API at it, verify `/readyz` and a sample artifact download.
