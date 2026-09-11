PHASE: 3 / Chat + files
STATUS: COMPLETE

Implemented
- Tables (migration 0003): conversations, messages, message_attachments, assets, asset_versions, artifacts, artifact_versions. Indexes `messages(conversation_id, created_at)`, `artifacts(project_id, created_at)` (spec §10).
- Conversations: list/create/rename/archive/search per project; a conversation holds many agents; messages keep the explicit slash command visible; user messages can attach assets and artifacts; assistant messages link `run_id`, `agent_id`, `agent_version_id`.
- Assets: multipart upload with MIME allowlist, size cap, extension/MIME match and filename sanitisation; image dimensions sniffed; the asset row is created only after the object exists in storage (spec §19 "Upload failure"); new versions; signed downloads (`GET /assets/{id}/download` → short-lived URL).
- Artifacts: versioned outputs with lineage (`run_id`, `node_run_id`, `produced_by_agent_version_id`, `parent_artifact_id`), status machine draft → generated → qc_failed/approved → final → archived, approve endpoint, lineage tree, signed downloads.
- Web: chat page (conversation sidebar with new/search/rename/archive, thread with agent badges and artifact cards, composer), assets page (upload/list/download), artifacts page (filter, approve, mark final, lineage).

Tests
- `tests/api/test_chat_files.py` — 3 tests: chat persistence + search + archive; upload validation (bad type, extension mismatch, empty, traversal), versions, signed download + tamper + tenant isolation, attachments; artifact lifecycle + illegal transitions + lineage.

Assumptions / limitations
- Message search uses `ILIKE`; add `pg_trgm` for large projects.
- Storage keys are namespaced `org/<org>/projects/<project>/…`; deleting a project cascades rows but object cleanup is a scheduled job (not in V0).
