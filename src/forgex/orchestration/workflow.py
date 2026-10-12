"""Workflow state machine (spec sections 12, 53).

Transitions are explicit; nothing may skip phases or leave a terminal
state. The repair loop is a first-class path: TESTING and SUPERVISING
can both fall into REPAIRING, which returns to REVIEWING/TESTING/BUILDING.
"""

from __future__ import annotations

from forgex.schemas.error import WorkflowError
from forgex.schemas.project import WorkflowStatus

ALLOWED_TRANSITIONS: dict[WorkflowStatus, frozenset[WorkflowStatus]] = {
    WorkflowStatus.INITIALIZING: frozenset(
        {
            WorkflowStatus.ANALYZING,
            WorkflowStatus.PLANNING,
            WorkflowStatus.BUILDING,
            WorkflowStatus.TESTING,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
        }
    ),
    WorkflowStatus.ANALYZING: frozenset(
        {
            WorkflowStatus.RESEARCHING,
            WorkflowStatus.PLANNING,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
        }
    ),
    WorkflowStatus.RESEARCHING: frozenset(
        {WorkflowStatus.PLANNING, WorkflowStatus.FAILED, WorkflowStatus.CANCELLED}
    ),
    WorkflowStatus.PLANNING: frozenset(
        {
            WorkflowStatus.ANALYZING,  # Re-planning
            WorkflowStatus.BUILDING,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
        }
    ),
    WorkflowStatus.BUILDING: frozenset(
        {
            WorkflowStatus.REVIEWING,
            WorkflowStatus.TESTING,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
        }
    ),
    WorkflowStatus.REVIEWING: frozenset(
        {
            WorkflowStatus.BUILDING,  # Per-task alternation
            WorkflowStatus.TESTING,
            WorkflowStatus.REPAIRING,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
        }
    ),
    WorkflowStatus.TESTING: frozenset(
        {
            WorkflowStatus.SUPERVISING,
            WorkflowStatus.REPAIRING,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
        }
    ),
    WorkflowStatus.SUPERVISING: frozenset(
        {
            WorkflowStatus.COMPLETED,
            WorkflowStatus.REPAIRING,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
        }
    ),
    WorkflowStatus.REPAIRING: frozenset(
        {
            WorkflowStatus.REVIEWING,
            WorkflowStatus.TESTING,
            WorkflowStatus.BUILDING,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
        }
    ),
    WorkflowStatus.COMPLETED: frozenset(),
    WorkflowStatus.FAILED: frozenset(),
    WorkflowStatus.CANCELLED: frozenset(),
}


def can_transition(current: WorkflowStatus, new: WorkflowStatus) -> bool:
    return new in ALLOWED_TRANSITIONS[current]


def transition(current: WorkflowStatus, new: WorkflowStatus) -> WorkflowStatus:
    """Validate a transition and return the new status.

    Raises WorkflowError on illegal transitions.
    """
    if new not in ALLOWED_TRANSITIONS[current]:
        msg = f"Illegal workflow transition: {current.value} -> {new.value}"
        raise WorkflowError(msg)
    return new
