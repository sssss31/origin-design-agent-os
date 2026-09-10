"""Export the shared JSON Schemas consumed by the web app from the API's domain models.

Run `make export-schemas` after changing app/domain/events.py or run_state.py; a test fails
when the exported files drift from the models.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.domain.events import EventType, ExecutionEvent
from app.domain.run_state import NODE_TRANSITIONS, RUN_TRANSITIONS, NodeState, RunState

OUT = Path(__file__).resolve().parents[3] / "packages" / "shared-schemas"


def build() -> dict[str, dict]:
    event_schema = ExecutionEvent.model_json_schema()
    event_schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    event_schema["$id"] = "https://origin.local/schemas/execution-event.schema.json"
    return {
        "execution-event.schema.json": event_schema,
        "run-states.json": {
            "run_states": [s.value for s in RunState],
            "node_states": [s.value for s in NodeState],
            "run_transitions": {k.value: sorted(v.value for v in vs) for k, vs in RUN_TRANSITIONS.items()},
            "node_transitions": {k.value: sorted(v.value for v in vs) for k, vs in NODE_TRANSITIONS.items()},
            "event_types": [e.value for e in EventType],
        },
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, content in build().items():
        (OUT / name).write_text(json.dumps(content, indent=2, sort_keys=True) + "\n")
        print(f"wrote {OUT / name}")  # noqa: T201


if __name__ == "__main__":
    main()
