"""WorkflowScheduler port: turns a workflow version's nodes/edges into execution batches.

V0 `SequentialScheduler` returns one node per batch, in stored order. A `DagScheduler`
returns topological levels whose nodes may execute in parallel. Run tables are identical.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class NodeSpec:
    id: str
    name: str
    kind: str  # e.g. "agent", "tool", "approval"
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EdgeSpec:
    source: str
    target: str
    condition: str | None = None


@runtime_checkable
class WorkflowScheduler(Protocol):
    name: str

    def plan(self, nodes: list[NodeSpec], edges: list[EdgeSpec]) -> list[list[NodeSpec]]: ...
