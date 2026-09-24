# Admin Console — architecture & plan

Goal: one place where an admin adds GPT agents, connects their APIs, tests them, and sees what they are doing. Users only ever see the chat; the console is admin-only (`capabilities.admin_console`).

## Information architecture

| Route | Purpose |
| --- | --- |
| `/admin` | Overview: agents connected / failing / missing keys, runs in the last 24 h, recent failures, quick actions. |
| `/admin/agents` | Agent table: name, `/command`, connection type, endpoint, key status, connection status, enabled, runs (24 h), last used. |
| `/admin/agents/new` | Add-agent wizard: 1) how it is called (OpenAI GPT agent · Custom HTTP endpoint · paste a cURL) → 2) identity + credentials → 3) test & enable. |
| `/admin/agents/{id}` | Agent detail with tabs: **Connection** (endpoint, key, options as a form), **Test** (send a message, see reply, latency, steps), **Activity** (recent runs, errors), **Settings** (name, command, description, enabled, default agent, delete). Origin-hosted agents keep an "Advanced editor" link (instructions, skills, tools, versions). |
| `/admin/activity` | Org-wide run log with filters (agent, status, date) and error messages. |
| `/admin/users`, `/admin/settings`, `/admin/audit` | Existing pages, kept. |
| Advanced group | Skills, Tools, AI Providers, Custom Integrations, Usage & Cost — the older Origin-hosted tooling, kept but out of the main path. |

## Backend (FastAPI)

Existing: agents CRUD, `PUT /admin/agents/{id}/connection`, `POST …/test-connection`, `POST /admin/agents/import-curl`, `POST /admin/seed/agent-registry`, org settings (`default_agent_id`), users, usage, audit.

Added for the console:

* `GET /admin/overview` — counts + recent failures (`app/api/v1/admin/console.py`).
* `GET /admin/activity?agent_id&status&limit` — run log across the organisation (status, agent, duration, error, conversation title).
* `POST /admin/agents/{id}/test-message {message}` — calls the agent through the same gateway the chat uses, without creating a conversation; returns the reply text, latency, whether a native session id came back, files count. Errors are returned as `error_code/error_message`, never raised.
* `DELETE /admin/agents/{id}` — allowed only when the agent has never been used (no runs); otherwise 409 with "disable it instead".

Secrets stay server-side: the browser only receives `configured` + `api_key_preview`.

## Data flow

```
Admin console ──PUT /agents/{id}/connection──▶ agents (endpoint, key → secret_refs, options)
Chat  /resize … ──POST /runs──▶ router ──▶ gateway ──▶ ExistingAgentProvider (openai_responses | http) ──▶ the agent's API
                                        └─▶ workflow_runs / node_runs / execution_events  ◀── Activity & Overview read these
```

## Extension points

* New agent protocol: add an adapter in `app/providers/existing/` implementing `ExistingAgentProvider`, register it in `providers/existing/registry.py`, add its option form in `apps/web/src/components/admin/ConnectionForm.tsx`.
* New console page: add a route under `apps/web/src/app/admin/` and a nav entry in `AdminShell.tsx`.
