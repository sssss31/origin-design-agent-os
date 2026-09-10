# shared-schemas

JSON Schemas generated from the API domain models (`apps/api/app/domain`) and consumed by
the web app (`apps/web/src/types`). Regenerate with `make export-schemas`; the API unit
test `test_shared_schemas.py` fails when they drift.

- `execution-event.schema.json` — wire format of one SSE / `execution_events` row.
- `run-states.json` — run/node state vocabularies, legal transitions and event types.
