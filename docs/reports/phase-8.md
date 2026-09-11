PHASE: 8 / Security, QA and deployment
STATUS: COMPLETE (staging deployment prepared; executed by the operator)

Implemented
- Rate limiting per user/IP (`RATE_LIMIT_PER_MINUTE`, Redis-backed when `REDIS_URL` is set) and per-organization run quotas (`quota_runs_per_day` in organization settings, default from `DEFAULT_RUNS_PER_DAY`).
- Governance: `api_usage` and `error_events` tables, `GET /admin/audit` (filterable), `GET /admin/usage` (runs/error rate/tokens/tool calls/recent errors) feeding the admin dashboard; audit page in the console.
- Automated security checks in CI and `make security`: bandit (0 findings at medium+), pip-audit (0 known vulnerabilities), npm audit (0 vulnerabilities). SVG parsing hardened with defusedxml.
- Tests: 85 API tests (unit, API, DB migrations round-trip, workflow, E2E journey `tests/e2e/test_user_journey.py`: login → project → upload → /resize → SSE → artifact → approve → audit → tenant isolation) + 6 web unit tests; production build.
- Load test script `scripts/load_test_sse.py` (concurrent runs streaming SSE; p50/p95 time-to-first-event and completion).
- Docs: `docs/SECURITY.md` (controls checklist, residual risks, backup policy), `docs/RUNBOOK.md` (environments, migrations, health, rollback), `infra/` compose + Dockerfiles with non-root users and migration entrypoint.

Security checks
- See `docs/SECURITY.md`; every item of spec §17 is mapped to a control and, where testable, to a test.

Assumptions / limitations
- Staging deployment itself (cloud account, DNS, secrets) is an operator action: `infra/docker-compose.yml` and the Dockerfiles are the deployable units; set the production profile variables from `.env.example` and run `python -m app.cli bootstrap-admin` then `seed-design-agents --provider-type openai`.
- The load test is a script to run against staging; numbers depend on the provider. Locally with the Echo provider a 7-node `/auto` run completes in ~100 ms.
