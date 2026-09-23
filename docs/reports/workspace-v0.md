# Origin Agent Workspace — V0 report

Date: 2026-09-23. Scope: the "ORIGIN AGENT WORKSPACE — V0" spec (§1–§42).

## What was built

| Spec area | Implementation |
| --- | --- |
| Agent Registry (§3, §27) | `agents` table extended (migration 0009): `connection_type` (`origin` / `openai_responses` / `http`), `api_endpoint`, encrypted key via `secret_refs` + `api_key_preview`, `connection_config`, `connection_status/message/tested_at`. `POST /admin/seed/agent-registry` creates the 8 commands. |
| Agent Gateway (§4, §6) | `app/services/agent_gateway.py`: `resolve_connection`, `load_context`, `prepare_files`, `call_agent`, `test_agent_connection`. One generic call path for every agent. |
| ExistingAgentProvider (§7) | `app/providers/existing/`: protocol `send_message / test_connection / validate_config`; adapters `OpenAIResponsesAgent` (public Responses API contract: `POST {base}/responses`, `previous_response_id`, `prompt.id`, SSE deltas, image/file inputs, image results) and `HttpJsonAgent` (configurable body/header templates and JSON response paths, SSRF-guarded). Registry in `providers/existing/registry.py`. |
| Native sessions & bounded context (§8–§10) | `agent_sessions.provider_session_id` stored per (conversation, agent); when absent the gateway sends the last ≤12 messages / 12k chars, other agents' replies prefixed `[Agent name]`. |
| Sticky agent & switching (§12–§14) | `conversations.active_agent_id`; follow-ups without a command go to the active agent; `/qc` switches and the chat shows "Active Agent changed: A → B". |
| Files & artifacts (§15–§16) | Assets/artifacts passed as `AgentFile` (presigned URL + bytes); agent-returned files persisted as artifacts by the `save` node. |
| Live operational nodes (§17–§19) | Plan `request → select → context → files → gateway:<agent> → save`; events `agent.selected`, `context.loaded`, `files.prepared`, `agent.started`, `response.streaming`, `node.completed/failed`; never chain-of-thought. Streamed over the existing SSE endpoint. |
| Chat history / My Work (§20–§23) | Sidebar grouped Today / Yesterday / date; `GET /work` (search + agent + date filters, Postgres `ILIKE`, no vector DB) and `GET /work/{conversation_id}`; page `/work`. |
| Admin → Agents (§27) | Connection tab first: name, command, description, connection type, endpoint, masked key, status, Test Connection, Save. Other tabs remain as "advanced". |
| API key security (§28) | Key normalised (Bearer token extracted from a pasted cURL), stored encrypted, only `configured` + `••••••••X82K` preview returned. |
| Error handling (§31–§32) | Unknown command → `agent_unavailable` with the available commands; adapter errors → node failed with "<Agent> could not complete the request. Retry."; run stored `failed`; the user message is kept and retry re-uses it. |
| Pages (§39) | `/login`, `/chat`, `/chat/{id}`, `/work`, `/admin/agents`. Login now lands on `/chat`. |

## Proof (definition of done, §41)

* Automated: `tests/api/test_workspace_v0.py::test_v0_definition_of_done` (mock HTTP agent) and `tests/unit/test_existing_providers.py`. Full API suite: 126 passed with SQLAlchemy warnings as errors; mypy and bandit clean; web lint, tsc and `next build` clean.
* Manual, in the browser against a real external HTTP endpoint (`https://httpbin.org/anything` configured as an `http` agent for `/resize` and `/qc`): login → new chat → `/resize` → reply streamed → follow-up stayed with Resize Agent and `context.loaded` carried 2 history messages → `/qc` switched with the banner → activity panel showed the six operational nodes with timings → My Work listed the conversation with both agents, message and file counts → Admin → Agents Connection tab showed the masked key and "Connected" after Test Connection.

## Contract note (§42)

No real GPT-agent contract or key was available in this environment. The OpenAI adapter follows the public Responses API documentation and the HTTP adapter is fully configurable (body template, header, response paths). When the real agents' endpoints are known, point `api_endpoint` at them and adjust `connection_config` — no code change is expected for either documented shape; if an agent uses a different protocol, add one adapter in `app/providers/existing/` and register it.

## Not built (by spec)

Manager agent, workflow builder, skills marketplace, pricing dashboard, vector search. The earlier Origin-hosted agents and admin pages remain available under `/app` and the other admin tabs.
