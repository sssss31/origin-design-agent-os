"""Run and node state machines (spec §9). Projections of `execution_events`.

The transition tables are the single place that defines what is legal. Services call
`assert_run_transition` / `assert_node_transition` before persisting a change.
"""

from __future__ import annotations

from enum import StrEnum


class RunState(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING_FOR_USER = "WAITING_FOR_USER"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class NodeState(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    WAITING_FOR_USER = "WAITING_FOR_USER"
    SKIPPED = "SKIPPED"


RUN_TRANSITIONS: dict[RunState, frozenset[RunState]] = {
    RunState.QUEUED: frozenset({RunState.RUNNING, RunState.CANCELLED, RunState.FAILED}),
    RunState.RUNNING: frozenset(
        {RunState.WAITING_FOR_USER, RunState.SUCCEEDED, RunState.FAILED, RunState.CANCELLED}
    ),
    RunState.WAITING_FOR_USER: frozenset(
        {RunState.QUEUED, RunState.RUNNING, RunState.CANCELLED, RunState.FAILED}
    ),
    RunState.SUCCEEDED: frozenset(),
    RunState.FAILED: frozenset({RunState.QUEUED}),  # explicit retry re-queues a failed run
    RunState.CANCELLED: frozenset(),
}

NODE_TRANSITIONS: dict[NodeState, frozenset[NodeState]] = {
    NodeState.PENDING: frozenset({NodeState.RUNNING, NodeState.SKIPPED, NodeState.FAILED}),
    NodeState.RUNNING: frozenset({NodeState.SUCCEEDED, NodeState.FAILED, NodeState.WAITING_FOR_USER}),
    NodeState.WAITING_FOR_USER: frozenset({NodeState.RUNNING, NodeState.FAILED, NodeState.SKIPPED}),
    NodeState.FAILED: frozenset({NodeState.PENDING}),  # retry of a safe node
    NodeState.SUCCEEDED: frozenset(),
    NodeState.SKIPPED: frozenset(),
}

TERMINAL_RUN_STATES = frozenset({RunState.SUCCEEDED, RunState.FAILED, RunState.CANCELLED})
TERMINAL_NODE_STATES = frozenset({NodeState.SUCCEEDED, NodeState.FAILED, NodeState.SKIPPED})


class IllegalTransition(ValueError):
    pass


def can_transition_run(current: RunState, target: RunState) -> bool:
    return target in RUN_TRANSITIONS[current]


def can_transition_node(current: NodeState, target: NodeState) -> bool:
    return target in NODE_TRANSITIONS[current]


def assert_run_transition(current: RunState | str, target: RunState | str) -> RunState:
    cur, tgt = RunState(current), RunState(target)
    if not can_transition_run(cur, tgt):
        raise IllegalTransition(f"run cannot go from {cur} to {tgt}")
    return tgt


def assert_node_transition(current: NodeState | str, target: NodeState | str) -> NodeState:
    cur, tgt = NodeState(current), NodeState(target)
    if not can_transition_node(cur, tgt):
        raise IllegalTransition(f"node cannot go from {cur} to {tgt}")
    return tgt


def derive_run_state(node_states: list[NodeState], *, cancelled: bool = False) -> RunState:
    """Projection rule: what the run state is given its nodes."""
    if cancelled:
        return RunState.CANCELLED
    if not node_states:
        return RunState.QUEUED
    if any(s is NodeState.WAITING_FOR_USER for s in node_states):
        return RunState.WAITING_FOR_USER
    if any(s is NodeState.FAILED for s in node_states):
        return RunState.FAILED
    if any(s is NodeState.RUNNING for s in node_states):
        return RunState.RUNNING
    if all(s in {NodeState.SUCCEEDED, NodeState.SKIPPED} for s in node_states):
        return RunState.SUCCEEDED
    return RunState.RUNNING if any(s is not NodeState.PENDING for s in node_states) else RunState.QUEUED
