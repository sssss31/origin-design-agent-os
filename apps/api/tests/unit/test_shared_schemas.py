"""The exported shared schemas must match the domain models (run `make export-schemas`)."""

import json
from pathlib import Path

import pytest
from scripts.export_schemas import OUT, build


@pytest.mark.parametrize("name", ["execution-event.schema.json", "run-states.json"])
def test_shared_schema_in_sync(name: str) -> None:
    path: Path = OUT / name
    assert path.exists(), f"{path} missing; run `make export-schemas`"
    assert json.loads(path.read_text()) == build()[name], f"{name} is stale; run `make export-schemas`"
