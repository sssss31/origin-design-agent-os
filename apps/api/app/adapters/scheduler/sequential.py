from __future__ import annotations

from app.ports.scheduler import EdgeSpec, NodeSpec


class SequentialScheduler:
    """V0: one node per batch in stored order. Edges are ignored (but stored)."""

    name = "sequential"

    def plan(self, nodes: list[NodeSpec], edges: list[EdgeSpec]) -> list[list[NodeSpec]]:  # noqa: ARG002
        return [[node] for node in nodes]
