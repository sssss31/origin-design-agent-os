PHASE: 2 / Admin configuration core
STATUS: COMPLETE

Implemented
- Tables (migration 0002): ai_providers, provider_models, tools, tool_versions, tool_permissions, skills, skill_versions, skill_files, agents, agent_versions, agent_skill_bindings, agent_tool_bindings, agent_handoffs. Partial unique index `uq_agents_active_command` enforces one active agent per command per organization (spec §10).
- Draft/publish/rollback for agents and skills: editing an active entity creates a draft version (bindings copied), `POST …/publish` runs a validation gate and switches `active_version_id` atomically, `POST …/publish {version_id}` re-activates an older published version (rollback). Historical runs will reference the exact `agent_version_id`.
- Agent bindings live on the agent version: skills (priority, pin-or-follow-active, variable overrides), tools (the permission to call; per-agent settings and call limits) and handoffs (routing hint, failure route).
- Providers: write-only `POST /admin/providers/{id}/secret` stores the key through `SecretStore` (Fernet ciphertext in `secret_refs`); responses carry `has_secret` + a hashed fingerprint only; `POST …/test` performs a minimal authenticated request (`GET /models` for OpenAI) and stores health status; `PUT …/models` sets the allowlist and default model; rotation bumps the secret version.
- Tools: versioned definitions with executor type (internal_function | http_api | mcp | sandbox); schema/config changes create a new published version; optional write-only credential; role/workspace permission rows.
- Prompt composer (`services/composer.py`) implementing the spec §5 order; `AgentFactory` resolves provider/model, skill versions, tool specs and composes instructions into an immutable `RuntimeAgent`.
- Sandbox `POST /admin/agents/{id}/test`: runs the draft/active version through the registered runner for the provider type (Echo now, OpenAI in Phase 4) and returns a safe trace (sections, tools, output, clarification, defaults) — no reasoning, no provider payloads.
- `GET /api/v1/agents/commands` for members: active commands appear in the UI immediately after publish.
- Admin UI: dashboard, Agents list/create, agent editor with General · Instructions · Skills · Tools · Model · Connections · Schemas · Versions · Test tabs, Skills list/editor (instructions, variables, required tools, knowledge files, versions), Providers (add, write-only key, test, allowlist), Tools (create, edit-as-new-version, secret, permissions). Project page shows the live command list.
- Audit rows for every change: provider.created/updated/secret_set/tested/models_set, tool.*, skill.created/updated/draft_saved/published/rolled_back/file_added, agent.created/updated/draft_saved/published/rolled_back/disabled/enabled/skill_attached/…/tested.

Files created/changed
- apps/api/app/models/{providers,tools,skills,agents}.py, models/__init__.py
- apps/api/app/schemas/admin.py
- apps/api/app/services/{providers,tools,skills,agents,agent_factory,composer,admin_serializers}.py
- apps/api/app/api/v1/admin/{__init__,providers,tools,skills,agents}.py, api/v1/agents.py, api/v1/router.py, core/deps.py, core/errors.py (JSON-safe validation details)
- apps/api/alembic/versions/0002_admin_configuration_core.py
- apps/api/tests/unit/test_composer.py, tests/api/test_admin_config.py, tests/conftest.py (put/delete helpers)
- apps/web/src/types/admin.ts, lib/api/admin.ts, components/admin/AdminShell.tsx, components/ui/{Tabs,JsonField}.tsx, app/admin/{page,agents/page,agents/[agentId]/page,skills/page,skills/[skillId]/page,providers/page,tools/page}.tsx, app/app/projects/[projectId]/page.tsx

Database migrations
- revision 0002 `admin configuration core` (upgrade/downgrade verified; circular entity↔version FKs created with explicit `create_foreign_key` after both tables exist).

API routes added
- GET/POST /api/v1/admin/providers · GET/PATCH /admin/providers/{id} · POST /admin/providers/{id}/secret · POST /admin/providers/{id}/test · GET/PUT /admin/providers/{id}/models
- GET/POST /api/v1/admin/tools · GET/PATCH /admin/tools/{id} · POST /admin/tools/{id}/secret · POST /admin/tools/{id}/permissions · DELETE /admin/tools/{id}/permissions/{permission_id}
- GET/POST /api/v1/admin/skills · GET/PATCH /admin/skills/{id} · POST /admin/skills/{id}/versions · POST /admin/skills/{id}/publish · POST /admin/skills/{id}/files
- GET/POST /api/v1/admin/agents · GET/PATCH /admin/agents/{id} · POST /admin/agents/{id}/versions · POST /admin/agents/{id}/publish · POST /admin/agents/{id}/test · POST/DELETE /admin/agents/{id}/skills/{skill_id} · POST/DELETE /admin/agents/{id}/tools/{tool_id} · POST/DELETE /admin/agents/{id}/handoffs/{target_agent_id}
- GET /api/v1/agents/commands

Tests
- `cd apps/api && .venv/bin/python -m pytest -q` — result: 73 passed, 0 failed (10 new: composer order/determinism/variables; provider secret write-only + encrypted + rotation + test + allowlist; full publish/rollback/commands flow; skill file upload + validation; admin role + tenant isolation; command validation).
- `ruff check`, `ruff format --check`, `mypy app` — clean (98 files).
- `cd apps/web && npm run lint && npm run typecheck && npm test && npm run build` — clean; 3 vitest tests; build succeeds with the six new admin routes.

Manual verification (browser, dev servers on :8010/:3010)
- Admin → Providers: added "Echo Provider", Test connection → health ok, allowlist `echo-1` with default saved.
- Admin → Skills: created "Brand & Asset Lock", published → active v1.
- Admin → Agents: created "Copy Agent" `/copy`, Model tab picked provider + allowlisted model, Skills tab attached the skill, Publish with change note → active v1.
- Test tab: sandbox run returned sections `platform_rules → agent_instructions → skill:brand-asset-lock@1` (833 chars), tools none, echo output, no reasoning.
- Project page: "Available commands" shows `/copy Copy Agent` immediately, served by `GET /api/v1/agents/commands` — no redeploy.

Security checks
- API key never returned: response schemas have no secret field; tests assert the key string is absent from every response and that `secret_refs.ciphertext` does not contain it.
- Provider test reads the key server-side through `SecretStore.reveal()` only.
- Admin routes require the organization admin role (403 otherwise); every entity query is filtered by organization (404 across tenants); a draft cannot reference another organization's provider.
- Skill knowledge uploads are MIME-allowlisted and size-capped; stored under `org/{org_id}/skills/…` keys.
- Publish gate refuses: empty instructions, missing/disabled provider, model outside the allowlist, command clashes with another active agent, inactive skills/tools, unknown handoff targets.

Assumptions / limitations
- Provider secrets use the Fernet-in-DB backend by default; a managed secret manager is a `SecretStore` adapter away (env backend exists).
- The OpenAI runner is not registered yet (Phase 4); sandbox tests against an OpenAI provider return 503 `runner_unavailable`. The Echo provider type exists for offline testing.
- Tool permissions (`tool_permissions`) are stored and editable; enforcement at run time (spec §12 step 4) lands with the run pipeline in Phase 4/5.
- Skill knowledge files are stored and versioned but not yet chunked/indexed for retrieval (Phase 4 context manager).
- Admin UI edits JSON schemas as raw JSON with inline validation; a form builder is out of V0 scope.

Next phase prerequisites
- Phase 3 tables: conversations, messages, message_attachments, assets, asset_versions, artifacts, artifact_versions; multipart uploads reuse the storage key layout and MIME/size validation introduced here.
