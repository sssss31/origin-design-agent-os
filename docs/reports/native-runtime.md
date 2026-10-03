# Execution architecture: Workspace Trigger vs Origin Native

Brief: "Agent output must exist inside Origin." The ChatGPT Workspace Agents API cannot provide it, so
Origin gained a second runtime and an explicit per-agent `execution_mode`.

## Phase 1 — the Workspace Agent integration, as it is (unchanged)

`POST https://api.chatgpt.com/v1/workspace_agents/{agtch_id}/trigger` with `{"input", "conversation_key"}`
and `OpenAI-Beta: workspace_agent_runs=v1` → `202 {"conversation_url", "agent_trigger_run_id"}`;
`GET …/runs/{apirun_id}` → `{"id", "status", "created_at", "agent_id", "api_trigger_id", "conversation_url", "error"}`.
No field carries the reply, files or images ("The agent's response cannot currently be retrieved through the
API"); no file input; no webhook/destination; no streaming. Origin records this as an **external result**.

## What changed

| Area | Change |
|---|---|
| DB (0011) | `agents.execution_mode` (`origin_native` / `workspace_trigger`), `agents.native_config`, `agents.native_api_key_secret_ref_id` + preview, `agents.workspace_agent_id`; `conversations.current_artifact_id` |
| Runtime dispatch | `agent_gateway.resolve_connection`: a Workspace agent in `origin_native` mode runs through the OpenAI Responses runtime with its own instructions/model/key (`native_connection`). Other connection types already return their payload and are `origin_native` by definition |
| Normalized result | node/run `result_json.result_type` = `native_result` or `external_result`, `external_url`, `provider_response_id`; the assistant message carries the same in `metadata_json` |
| Events | `tool.started`/`tool.completed` (`image_generation`), `artifact.preview` (partial renders), `artifact.created`; node names `"<Agent> selected"`, `"Source image loaded"` / `"Current design loaded"` |
| Context | a follow-up without attachments receives `conversations.current_artifact_id` (or the last uploaded asset); the native session (`previous_response_id`) continues |
| Admin | `PUT /admin/agents/{id}/runtime`, `POST /admin/agents/{id}/test-native` (multipart prompt + image → inline result); Runtime tab with execution mode, instructions, model, key, image options, **Test Native Agent** |
| Chat | external results render as an external-result card (status + link); native results render text + artifacts; the process log shows the application steps and stays with the reply |

## Acceptance (mocked OpenAI, local UI) — all passing

1. `/resize` + MRFW image + "resize 16:9" (origin_native): steps `Request received → Resize Agent selected →
   Conversation context loaded → Source image loaded → Resize Agent working (Image generation started → Image
   generated → Artifact stored) → Response saved`; reply text + the generated image inside Origin; no ChatGPT link.
2. "Make the same design 4:5." without re-uploading: `Current design loaded`, the previous result is sent as
   `input_image`, a new image is produced.
3. Browser refresh: original, both results, messages, the process log and the active agent remain.

API tests: `tests/api/test_native_runtime.py` (mode validation, test-native, external vs native results,
follow-up context, persistence), `tests/api/test_image_previews.py`.

## Migration of Resize2 (live) — to do by an admin

1. Admin → Agents → Resize2 → **Runtime**: paste the agent's ChatGPT instructions, model `gpt-5`,
   an OpenAI Platform API key (`sk-…`), save.
2. **Test Native Agent** with the MRFW poster and "resize 16:9" — the image must appear in the panel.
3. Parity check (brief §26): run the same input in ChatGPT and in the panel; compare composition, text,
   ratio, brand consistency. Adjust instructions / image options until acceptable.
4. Select **Origin Native** → Save. From then on `/resize2` answers inside Origin. Workspace Trigger remains
   selectable as a fallback. Other agents stay as they are until each passes the same test.

## Final Resize2 runtime (brief: "Origin-native execution architecture")

- **Not the Workspace instance.** `native_connection()` builds Origin's own Responses API runtime from the
  agent's server-side configuration (`agents.native_config`: `instructions`, `model`, `image_model`,
  `image_action`, `image_quality`, optional pinned `image_options.size`; the key in `secret_refs`).
  The Workspace trigger remains as legacy `execution_mode = workspace_trigger`.
- **Source image**: uploaded to Origin storage, read back server-side and sent as `input_image`
  (base64 data URL) — never only the filename.
- **Real dimensions** (`app/domain/image_sizes.py`): the request's ratio/words/pixels pick the tool `size`:
  gpt-image-2.x → multiples of 16 within 1:3…3:1 (16:9 → 1792x1008, 4:5 → 1200x1504, 1:1 → 1344x1344,
  9:16 → 1008x1792); older image models → 1536x1024 / 1024x1536 / 1024x1024. An admin-pinned size wins.
- **Receive → store → return**: `image_generation_call.result` is decoded server-side, stored as an
  artifact (width/height sniffed), `conversations.current_artifact_id` updated, the reply carries
  `result_type = native_result`, `provider_response_id`, the artifact attachments; an image-only reply gets
  the line "Completed the 16:9 adaptation." and the file is named `<agent>-16x9.png`.
- **Multi-turn**: `previous_response_id` + the current artifact as `input_image` + the new request.
- **Admin → Runtime**: status summary (Runtime, Model, Image model, Instructions, API credential, Image
  input, Image generation, Status: Ready after a successful **Test Runtime**), the key is write-only.
