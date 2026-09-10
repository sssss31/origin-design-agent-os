"""Topological-level scheduler: nodes in the same level have no dependency on each other."""

from __future__ import annotations

from collections import defaultdict, deque

from app.ports.scheduler import EdgeSpec, NodeSpec


class CyclicWorkflow(ValueError):
    pass


class DagScheduler:
    name = "dag"

    def plan(self, nodes: list[NodeSpec], edges: list[EdgeSpec]) -> list[list[NodeSpec]]:
        by_id = {n.id: n for n in nodes}
        indegree: dict[str, int] = {n.id: 0 for n in nodes}
        children: dict[str, list[str]] = defaultdict(list)
        for edge in edges:
            if edge.source not in by_id or edge.target not in by_id:
                raise ValueError(f"edge references unknown node: {edge.source}->{edge.target}")
            children[edge.source].append(edge.target)
            indegree[edge.target] += 1
        level = deque(
            sorted(
                (nid for nid, d in indegree.items() if d == 0), key=lambda i: [n.id for n in nodes].index(i)
            )
        )
        batches: list[list[NodeSpec]] = []
        seen = 0
        while level:
            batch_ids = list(level)
            level.clear()
            batches.append([by_id[i] for i in batch_ids])
            seen += len(batch_ids)
            for nid in batch_ids:
                for child in children[nid]:
                    indegree[child] -= 1
                    if indegree[child] == 0:
                        level.append(child)
        if seen != len(nodes):
            raise CyclicWorkflow("workflow graph contains a cycle")
        return batches
