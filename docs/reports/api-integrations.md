# GPT Agent API / cURL Integration — implementation report

Scope: the "Implement GPT Agent API / cURL Integration" brief (Admin → API Integrations, OpenAI +
custom REST providers, agent provider/model assignment, skills/tools, runtime, cURL import, usage
& cost, security). Built incrementally in eight phases on top of the existing V0 system; nothing that
already worked was rewritten.

## Phase summary

| Phase | Status | What landed |
|-------|--------|-------------|
| 1 Secret storage + OpenAI provider | COMPLETE | `app/providers/` adapter layer (`AIProvider`: execute / test_connection / validate_config / get_supported_models / model_capabilities / calculate_usage), `OpenAIProvider` with model-aware parameter filtering (reasoning vs chat vs image models, admin overrides), bounded exponential backoff for retryable errors only and never after a tool call, sanitized `ProviderError`; `key_preview` (`sk-proj-••••••••7Xk2`) + `environment` on providers (migration 0005). |
| 2 Provider Admin UI + connection testing | COMPLETE | `GET /admin/integrations/overview`, `GET/POST /admin/providers/{type\|id}/status\|test\|connection-test` (spec §2/§3 contracts), delete secret / delete provider (refused while in use), supported-models. Web: Admin → API Integrations with OpenAI card (🟢 Connected / 🔴 Connection Failed, Test Connection, Update Key, Manage Models, Disable, Delete) and the five-step Connect OpenAI wizard; spec §18 navigation. |
| 3 Agent provider/model assignment | COMPLETE | Agent editor "AI Provider" tab: provider, allowed-model dropdown (image models excluded), command, name, instructions, temperature / reasoning effort only when the model supports them, max output tokens, capability panel. Publish gate refuses image models and unsupported sampling parameters. |
| 4 Skills and tools | COMPLETE | Skill reorder (`PUT /admin/agents/{id}/skills/order`), enable/disable of skill and tool bindings without detaching, per-skill Edit/Test in the agent editor, `POST /admin/skills/{id}/test` (sandbox run with the skill draft injected). Data model unchanged: `agents → agent_versions → agent_skill_bindings → skills` and `agent_tool_bindings → tools`. |
| 5 `/agentname` runtime | COMPLETE | `/command` → active agent → exact agent version → provider row + secret → skills → bound tools → workspace context → composed instructions → provider adapter (retry, filtering) → tool calls (built-in or HTTP) → artifacts → usage row → assistant message. Runs without a key fail with `provider_secret_unavailable` and a sanitized message; `provider.retry` events appear in the timeline. |
| 6 cURL / custom REST | COMPLETE | `custom_integrations` + `integration_secrets` (migration 0006); cURL parser extracts credentials from headers, query strings, `-u` and JSON fields into encrypted secret references; template engine; SSRF guard; `HttpApiExecutor` (no redirects, bounded timeout/size, binary responses become artifacts); every integration auto-creates an `api.<slug>` tool so agents bind it like any other tool; admin pages Add Custom API (import or manual), detail (request editor, secrets, Test API Request → API → Response, assign to agents). |
| 7 Usage / cost telemetry | COMPLETE | `api_usage` extended with provider/agent/version/user/workspace/project/workflow/command, cached and reasoning tokens, image generations, requests, estimated USD cost, priced flag, status (migration 0007); `model_pricing` table (exact id or `prefix*`) editable from Admin → Usage & Cost; summary (today / month / 30d in the org's display currency), breakdown by agent / model / user / workspace / workflow / provider, recent calls; provider budgets (`monthly_budget_usd`, `max_requests_per_day`) enforced before each call; agent Test console with the spec §16 checklist and usage/cost. |
| 8 Security, tests, hardening | COMPLETE | Users (list, invite with one-time password, role, deactivate; last-admin and self-deactivate guards) and System Settings (global rules, display currency, FX rate, run quota, QC revisions, read-only outbound config); `docs/SECURITY.md` updated; `.env.example` documents the new settings; bandit clean. |

## Files changed (new or modified)

API: `app/providers/{__init__,base,openai_models,openai_provider,echo_provider}.py`, `app/adapters/{registry,tools_http}.py`,
`app/adapters/runners/openai_agents.py`, `app/core/{config,ssrf}.py`, `app/domain/{curl_parser,templates,events}.py`,
`app/models/{providers,integrations,workflows,__init__}.py`, `app/ports/{runner,secrets}.py`,
`app/schemas/{admin,integrations}.py`, `app/services/{providers,agents,agent_factory,skills,integrations,usage,admin_serializers}.py`,
`app/api/v1/admin/{__init__,providers,integrations,usage,organization,agents,skills}.py`, `app/workers/run_executor.py`,
`alembic/versions/0005_provider_key_preview_and_environment.py`, `0006_custom_integrations.py`, `0007_usage_cost_and_model_pricing.py`,
tests: `tests/unit/{test_providers,test_curl_and_templates}.py`, `tests/api/{test_integrations,test_usage_cost,test_admin_config,test_governance}.py`.

Web: `src/components/admin/{AdminShell,OpenAIConnectWizard,KeyValueEditor}.tsx`, `src/app/admin/integrations/page.tsx`,
`src/app/admin/integrations/custom/new/page.tsx`, `src/app/admin/integrations/custom/[integrationId]/page.tsx`,
`src/app/admin/{usage,users,settings}/page.tsx`, `src/app/admin/agents/[agentId]/page.tsx`, `src/app/admin/providers/page.tsx` (redirect),
`src/lib/api/{admin,integrations}.ts`, `src/types/{admin,integrations}.ts`.

## Database migrations

- 0005 — `ai_providers.key_preview`, `ai_providers.environment`
- 0006 — `custom_integrations`, `integration_secrets`
- 0007 — `api_usage` cost/attribution columns, `model_pricing`

## API endpoints added

- Providers: `GET /admin/providers/{type|id}/status`, `POST /admin/providers/{type|id}/test`, `POST /admin/providers/{ref}/connection-test`, `DELETE /admin/providers/{id}/secret`, `DELETE /admin/providers/{id}`, `GET /admin/providers/{id}/supported-models`
- Integrations: `GET /admin/integrations/overview`, `GET/POST /admin/integrations`, `POST /admin/integrations/parse-curl`, `POST /admin/integrations/import-curl`, `GET/PATCH/DELETE /admin/integrations/{id}`, `POST /admin/integrations/{id}/secrets`, `DELETE /admin/integrations/{id}/secrets/{name}`, `POST /admin/integrations/{id}/test`
- Agents/skills: `PUT /admin/agents/{id}/skills/order`, `POST /admin/skills/{id}/test` (agent `POST …/test` now returns steps + usage)
- Usage: `GET /admin/usage/summary`, `GET /admin/usage/breakdown?by=&range=`, `GET /admin/usage/calls`, `GET/PUT /admin/usage/pricing`, `DELETE /admin/usage/pricing/{id}`
- Organisation: `GET/POST /admin/users`, `PATCH /admin/users/{user_id}`, `GET/PUT /admin/settings`

## Tests / checks

- API: `pytest` — 112 passed (unit + API + migration round-trip), `ruff`, `mypy` (144 files), `bandit -ll` clean.
- Web: `eslint`, `tsc --noEmit`, `vitest`, `next build` clean.
- Browser: OpenAI wizard stores a key encrypted and reports a sanitized 🔴 failure for an invalid key against the real endpoint; cURL import of an httpbin call extracted the bearer token into a secret reference, created `api.httpbin_echo`, and Test API returned HTTP 200 with masked credentials; agent AI Provider tab shows capability-aware fields; Usage & Cost, Users and System Settings pages load.

## Security considerations

See `docs/SECURITY.md` (updated). Highlights: server-side calls only; Fernet-encrypted secrets with masked previews; RBAC (admin-only for every management route); retries bounded and side-effect aware; SSRF guard with https-only, private-address blocking and optional host allowlist; response size and timeout caps; sanitized logs and errors; budgets/quotas; audit rows for every change.

## Acceptance criteria (§24)

1–3 OpenAI key from UI, encrypted, never returned, testable — done. 4–7 create/edit agent, assign provider/model, attach skills/tools — done. 8–9 cURL import with secrets extracted and encrypted — done. 10–13 `/agentname` loads the agent, skills, tools and provider dynamically, executes server-side, replies in chat — done (verified with the Echo provider and mocked HTTP; a real OpenAI key was not available in this environment, so the OpenAI path is covered by unit tests with a fake runner and by the live 401 connection test). 14–15 conversation and artifacts persisted — done. 16–17 usage and estimated cost recorded and visible — done. 18 no code change for configuration — done. 19 agent versioning and rollback — pre-existing, extended (every AI Provider change creates a draft). 20 no secret in frontend/network/logs — tests assert it.

## Remaining work

- Live smoke test against OpenAI with a real key (the environment had none); the code path is unit-tested.
- Model prices must be entered by the admin (an empty pricing table marks calls as unpriced).
- Inbound webhooks / MCP executors are out of scope for this brief.
