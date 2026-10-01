# Chat reliability & agent routing — technical report (2026-10-01)

Brief: "/agent selects the agent like a model picker; follow-ups stay with it; the chat must never disappear; show the real process; render files; recover after refresh."

## Root causes found in the existing code

| Symptom | Root cause | Fix |
| --- | --- | --- |
| Chat "disappears" after a slash command / error | `useConversation` redirected to `/` whenever the initial load failed (any transient 401/timeout), and the home greeting rendered while a chat was still loading | No redirect: a load error shows a message with Retry; a "Loading chat…" state replaces the greeting flash |
| "/resize" became the prompt | A bare command created a run with an empty body; the executor fell back to the raw `user_input` (`"/resize"`), and the stored message content (with the command) was also replayed into the agent's history | Bare commands are rejected by the API (`empty_prompt`) and handled client-side as *select*; `user_input`, the gateway message and history now carry the body only |
| Responses not appearing after Retry | A retried run keeps its earlier events; the client treated the replayed `run.failed` of the previous attempt as final and ignored the new attempt | Terminal events are confirmed against the run status before the client stops listening |
| Chat stuck "working" forever | On the serverless host the run executes inside the SSE request; if the browser navigated away, the run stayed `RUNNING` (stale window was 15 min) | Stale runs (no progress for 150 s on serverless) are reaped to `FAILED (interrupted)` on read, so Retry appears; the client polls history if the stream drops |
| No visible agent selection | Agent switches only changed `active_agent_id` | A persistent `system` message ("Resize Agent selected") is written on every switch and rendered as a centred event |
| Files from agents never rendered | HTTP adapter sent object body templates as Python `repr()`, so file-returning configs broke; the thread had no artifact rendering | Object templates are serialised as JSON (raw `{{history}}`/`{{files}}`); `ArtifactCard` previews images and shows file cards with Open/Download |
| Titles like "4:5" | Title = first message body | Title = `<Agent>: <request>` |
| Unknown command silently created a bad run | No client-side validation | `parseSlash` → inline hint with suggestions, nothing sent |
| Local SSRF guard rejected public hosts on NAT64 networks | `64:ff9b::/96` addresses counted as reserved | NAT64 addresses are judged by their embedded IPv4 |

Verified **not** a cause: SSE through the Vercel rewrite streams correctly (ticks arrive 1 s apart via `/healthz/stream`).

## Files changed

API: `app/services/runs.py` (empty-command guard, command-free `user_input`, `reap_if_stale`), `app/services/conversations.py` (system event on switch, agent-aware titles), `app/services/agent_gateway.py` (history without commands), `app/workers/run_executor.py` (prompt = body), `app/providers/existing/http_json.py` (object body templates), `app/core/ssrf.py` (NAT64), `app/core/config.py` (serverless stale window), `app/api/v1/health.py` (stream diagnostic). Tests: `tests/api/test_chat_routing.py`, additions in `test_existing_providers.py`, `test_ssrf.py`, `test_chat_files.py`.

Web: `src/lib/slash.ts` (+ tests), `src/components/chatbot/Composer.tsx`, `useConversation.ts`, `Thread.tsx`, `ArtifactCard.tsx` (new), `ChatApp.tsx`, `src/types/chat.ts`.

## Database

No schema changes. Existing tables already cover the brief's model: `conversations.active_agent_id`, `messages` (role user/assistant/system, `command`, `agent_id`, `metadata_json`), `message_attachments` (asset/artifact), `workflow_runs`/`node_runs` (lifecycle), `execution_events` (ordered events), `agent_sessions` (`provider_session_id` = provider thread/session), `artifacts`/`artifact_versions`, `assets`.

## How routing works now

`parseSlash(text, agents)` in the composer: `/resize` → `PUT /conversations/{id}/active-agent` (system event, no run); `/resize text` → `POST /runs` with the full text, the API stores `command` + body and routes explicitly; plain text → the conversation's active agent (server default: org default agent, else first connected agent); unknown → hint. The dropdown uses the same `select()`.

## Sessions / context

Per (conversation, agent) an `agent_sessions` row keeps the provider's own continuation id (OpenAI `previous_response_id`, ChatGPT `conversation_key`, HTTP `session_id`). Without one, the gateway sends the last ≤12 messages (commands stripped, other agents' turns labelled). Origin's history is always persisted independently of the provider.

## Streaming

Run events (`run.started`, `node.*`, `agent.selected`, `context.loaded`, `files.prepared`, `agent.started`, `response.streaming`, `artifact.created`, `run.completed/failed/cancelled`) are persisted in order and fanned out over SSE (`GET /runs/{id}/events`, replay from `after`). The client absorbs events by sequence number, falls back to polling `events/history` + run status if the stream ends early, and only finalises when the run status is terminal.

## Files

Uploads → `POST /projects/{id}/assets` → attachment on the user message → passed to the agent as data URLs / presigned URLs. Agent outputs (`ProducedFile`) → artifacts → attachments on the assistant message → `ArtifactCard` (image preview, Open/Download via signed URL). Unknown binary types are never rendered as text.

## What the providers expose

* OpenAI Responses API: streamed text deltas, image outputs, `previous_response_id` — full chat experience.
* Custom HTTP JSON: whatever the endpoint returns by configured paths (text, session id, files).
* **ChatGPT Workspace Agents (trigger API): no reply text, no tool events, no files via API.** Origin shows Origin-owned lifecycle states (request sent → status polling → completed) plus the ChatGPT conversation link. This is a provider limitation, documented by OpenAI.

## Security

Tokens stay server-side (encrypted `secret_refs`); the browser gets only `configured` + masked preview; errors never echo tokens. Found/fixed: none new; the NAT64 change keeps loopback/metadata/private targets blocked.

## Tests / build

API: 147 tests, ruff, mypy, bandit. Web: eslint, tsc, 14 unit tests, `next build`. Browser (local, httpbin stand-in agents): bare `/resize` select · `/resize text` cleaned prompt · follow-up same agent · `/qc` switch keeps history · `/resize` switch back · refresh restores · error + Retry · unknown command hint · upload chip persists · agent image artifact renders.

## Remaining limitations

ChatGPT Workspace Agent answers live in ChatGPT; serverless cold start ≈ 1.5–2 s; uploads on the serverless host are ephemeral unless `STORAGE_BACKEND=s3`; two-tab concurrent editing is safe (server is the source of truth) but not live-synced between tabs.
