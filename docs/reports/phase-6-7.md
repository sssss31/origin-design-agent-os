PHASE: 6 + 7 / Eight design agents, tool integrations, workflow hardening
STATUS: COMPLETE

Implemented
- Built-in tools (`app/tools/builtin.py`, registered as editable `tools` rows on seed): asset.list, artifact.list, image.inspect, file.inspect (PDF page sizes, SVG structure via defusedxml), svg.inspect, image.resize (adaptive cover-crop / strict letterbox to 1:1, 4:5, 9:16, 16:9, 3:4, 2:3, banner, A4 or WxH), image.generate (provider image API with the run's credentials), qc.checklist (deterministic: decodable, size/aspect, minimum size, blank, safe-margin crowding, file size → structured report), export.package (png/jpg/pdf with DPI, dimension/size validation, marks final), copy.constraints.
- Seed (`app/seeds/design_agents.py`, CLI `seed-design-agents`, `POST /admin/seed/design-agents`, dashboard button): eight skills (§21) and eight agents (§13) with instructions, requirement/input schemas (Resize contract from §13), QC output schema, tool bindings, handoffs including QC failure routes back to Resize/Master, Manager handoffs to every specialist. Idempotent; keeps an admin's existing agent on a command and wires handoffs to it.
- Manager sequential delegation: structured `{"plan": [...]}` from the model or a deterministic keyword plan over the manager's handoffs; specialist nodes are appended to the same run and executed in order; delegation is limited to declared handoffs.
- QC loop: a `qc_report` in an agent's structured output sets checked artifacts to `qc_failed`/`generated`, stores the report on the artifact version, and (within `max_revisions`, default 1) re-queues the producing agent with the findings followed by a QC re-check.
- Artifact hardening: parent lineage from tool metadata, approve/final states, `GET /artifacts/{id}/lineage`, export refuses mismatched dimensions or oversize files and never marks an unvalidated file final.

Tests
- Tool paths are exercised in `test_runs.py` (resize → 2 artifacts, qc pass/fail, export pdf + refusal) and `test_governance.py` (seed: 8 commands, handoffs, skill/tool bindings, idempotency, existing-command skip).

Assumptions / limitations
- image.generate requires an OpenAI key (image model configurable via tool settings); not exercised in CI.
- Editable/SVG reconstruction is inspection + rules based (spec non-goal: no pixel-perfect raster→vector engine); confidence is reported by the agent.
