from __future__ import annotations

import pytest

from forgex.orchestration.workflow import ALLOWED_TRANSITIONS, can_transition, transition
from forgex.schemas.error import WorkflowError
from forgex.schemas.project import WorkflowStatus as WS


def test_happy_path_chain():
    chain = [
        WS.INITIALIZING, WS.ANALYZING, WS.RESEARCHING, WS.PLANNING, WS.BUILDING,
        WS.REVIEWING, WS.TESTING, WS.SUPERVISING, WS.COMPLETED,
    ]
    current = chain[0]
    for nxt in chain[1:]:
        current = transition(current, nxt)
    assert current is WS.COMPLETED


def test_repair_loop_transitions():
    assert can_transition(WS.TESTING, WS.REPAIRING)
    assert can_transition(WS.SUPERVISING, WS.REPAIRING)
    assert can_transition(WS.REPAIRING, WS.TESTING)
    assert can_transition(WS.REPAIRING, WS.BUILDING)


def test_invalid_transition_rejected():
    with pytest.raises(WorkflowError):
        transition(WS.PLANNING, WS.TESTING)


def test_terminal_states_locked():
    for terminal in (WS.COMPLETED, WS.FAILED, WS.CANCELLED):
        assert ALLOWED_TRANSITIONS[terminal] == frozenset()
        with pytest.raises(WorkflowError):
            transition(terminal, WS.BUILDING)


def test_every_active_state_can_fail_or_cancel():
    terminals = (WS.COMPLETED, WS.FAILED, WS.CANCELLED)
    for status in WS:
        if status in terminals:
            continue
        assert WS.CANCELLED in ALLOWED_TRANSITIONS[status], status
        assert WS.FAILED in ALLOWED_TRANSITIONS[status], status


def test_replanning_from_planning_allowed():
    assert can_transition(WS.PLANNING, WS.ANALYZING)


def test_cannot_replan_mid_build():
    with pytest.raises(WorkflowError):
        transition(WS.BUILDING, WS.ANALYZING)


def test_per_task_review_alternation_allowed():
    assert can_transition(WS.REVIEWING, WS.BUILDING)
