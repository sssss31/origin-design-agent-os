# Origin chatbot (Claude-style) — report

Date: 2026-09-23. Direction from the product owner: "a full Claude-like chatbot; internally we connect the GPT agents' API keys; when a user types `/agentname` the agent is called directly."

## What the product is now

* `/` — the chat. Greeting + composer on an empty chat; a Claude-style thread otherwise (user bubbles on the right, agent replies rendered as Markdown with avatar, name and Copy).
* `/c/{id}` — an existing chat. Sidebar lists chats grouped Today / Yesterday / Previous 7 days / Previous 30 days / Older, with search, rename and delete.
* `/settings/agents` — admin only: add/edit each agent (name, `/command`, description, how it is called, endpoint, API key, enabled), Test connection, and the default agent for plain messages. Keys are stored encrypted; the browser only ever sees `••••••••X82K`.
* `/login` — unchanged; lands on `/`.

Everything from the earlier workspace attempt that the owner did not want (activity panel, My Work, Files, three-pane layout) was removed. The older `/app` dashboard and `/admin` console still exist behind the account menu as "Advanced console" and can be deleted later.

## How a message flows

1. `/resize …` in the composer (or an agent picked from the agent menu, or `/` autocomplete).
2. `POST /conversations/{id}/runs` → the router picks the agent by command; with no command it uses the sticky agent of the chat, else the organisation's default agent (Settings), else the first connected agent, else the Manager.
3. The gateway calls the agent's own API with its stored key (`app/providers/existing/`), streaming the reply as `response.streaming` events (48-char chunks) that the page renders live.
4. The reply is saved as an assistant message tagged with the agent; the agent becomes the chat's active agent so follow-ups go to it without re-typing the command.
5. Errors show inline with Retry; Retry re-runs the same stored message (never duplicates it). Manual retry is allowed for any failed run.

## Fixes found while verifying in the browser

* Development runs without `ENCRYPTION_KEY` used to generate a fresh Fernet key on every process start, so every `uvicorn --reload` made all stored agent keys unreadable ("the stored credential cannot be read"). The key is now persisted in `apps/api/.data/dev-encryption.key` (git-ignored, mode 600). Production still requires `ENCRYPTION_KEY`.
* `POST /runs/{id}/retry` refused runs whose failed node was flagged non-retryable; a person pressing Retry (after an admin fixed the key) is now always allowed.

## Verification

* API: 127 tests pass (SQLAlchemy warnings as errors), ruff, mypy, bandit clean. New test: a plain message with no command goes to the default connected agent.
* Web: eslint, tsc and `next build` clean.
* Browser (stand-in agent = `https://httpbin.org/anything` echoing the message): new chat → `/resize` → reply rendered → Retry after a failure → `/qc` with Markdown (headings, list, code, table) rendered → settings page lists agents with masked keys and connection status.

## Still needed from the owner

The real GPT agents' endpoints and keys. Two call shapes are supported out of the box: OpenAI Responses API (base URL + prompt id in Options) and a generic HTTP JSON endpoint (configurable body/response paths). Anything else needs one adapter in `app/providers/existing/`.

## Addendum 2026-09-24 — Admin Console

Built per `docs/ADMIN_CONSOLE.md`: `/admin` overview (connected / failing / missing-key agents, messages in 24 h, recent failures), `/admin/agents` table, `/admin/agents/new` wizard (OpenAI GPT agent · custom HTTP · paste a cURL → details & key → test message → done), `/admin/agents/{id}` with Connection / Test / Activity / Settings tabs (the old multi-tab editor lives on as "Advanced editor"), `/admin/activity` run log with agent/status filters. New endpoints: `GET /admin/overview`, `GET /admin/activity`, `POST /admin/agents/{id}/test-message`, `DELETE /admin/agents/{id}` (unused agents only). Test: `tests/api/test_admin_console.py`.
