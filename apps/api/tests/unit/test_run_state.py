import pytest
from app.domain.run_state import (
    IllegalTransition,
    NodeState,
    RunState,
    assert_node_transition,
    assert_run_transition,
    derive_run_state,
)


def test_run_happy_path() -> None:
    assert assert_run_transition(RunState.QUEUED, RunState.RUNNING) is RunState.RUNNING
    assert assert_run_transition(RunState.RUNNING, RunState.SUCCEEDED) is RunState.SUCCEEDED


def test_run_clarification_pause_and_resume() -> None:
    assert_run_transition(RunState.RUNNING, RunState.WAITING_FOR_USER)
    assert_run_transition(RunState.WAITING_FOR_USER, RunState.QUEUED)  # re-enqueued after reply
    assert_run_transition(RunState.WAITING_FOR_USER, RunState.RUNNING)


def test_terminal_states_are_final_except_retry() -> None:
    with pytest.raises(IllegalTransition):
        assert_run_transition(RunState.SUCCEEDED, RunState.RUNNING)
    with pytest.raises(IllegalTransition):
        assert_run_transition(RunState.CANCELLED, RunState.RUNNING)
    assert_run_transition(RunState.FAILED, RunState.QUEUED)  # retry


def test_node_transitions() -> None:
    assert_node_transition("PENDING", "RUNNING")
    assert_node_transition(NodeState.RUNNING, NodeState.WAITING_FOR_USER)
    assert_node_transition(NodeState.WAITING_FOR_USER, NodeState.RUNNING)
    with pytest.raises(IllegalTransition):
        assert_node_transition(NodeState.SUCCEEDED, NodeState.RUNNING)
    with pytest.raises(IllegalTransition):
        assert_node_transition(NodeState.PENDING, NodeState.SUCCEEDED)


@pytest.mark.parametrize(
    ("nodes", "expected"),
    [
        ([], RunState.QUEUED),
        ([NodeState.PENDING, NodeState.PENDING], RunState.QUEUED),
        ([NodeState.SUCCEEDED, NodeState.RUNNING], RunState.RUNNING),
        ([NodeState.SUCCEEDED, NodeState.WAITING_FOR_USER], RunState.WAITING_FOR_USER),
        ([NodeState.SUCCEEDED, NodeState.FAILED, NodeState.PENDING], RunState.FAILED),
        ([NodeState.SUCCEEDED, NodeState.SKIPPED], RunState.SUCCEEDED),
        ([NodeState.SUCCEEDED, NodeState.PENDING], RunState.RUNNING),
    ],
)
def test_derive_run_state(nodes: list[NodeState], expected: RunState) -> None:
    assert derive_run_state(nodes) is expected


def test_cancel_overrides() -> None:
    assert derive_run_state([NodeState.RUNNING], cancelled=True) is RunState.CANCELLED
