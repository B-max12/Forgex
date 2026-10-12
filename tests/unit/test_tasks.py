from __future__ import annotations

import pytest

from forgex.schemas.error import TaskGraphError
from forgex.schemas.task import Task, TaskPriority, TaskStatus, ready_tasks, topological_order


def _tasks() -> list[Task]:
    return [
        Task(id="TASK-001", description="a", priority=TaskPriority.LOW),
        Task(id="TASK-002", description="b", depends_on=["TASK-001"]),
        Task(id="TASK-003", description="c", priority=TaskPriority.CRITICAL),
        Task(id="TASK-004", description="d", depends_on=["TASK-002", "TASK-003"]),
    ]


def test_topological_order_respects_dependencies():
    order = [t.id for t in topological_order(_tasks())]
    assert order.index("TASK-001") < order.index("TASK-002")
    assert order.index("TASK-002") < order.index("TASK-004")
    assert order.index("TASK-003") < order.index("TASK-004")
    assert sorted(order) == ["TASK-001", "TASK-002", "TASK-003", "TASK-004"]


def test_priority_breaks_ties_among_ready():
    order = [t.id for t in topological_order(_tasks())]
    # TASK-003 (critical) and TASK-001 (low) are both initially ready.
    assert order[0] == "TASK-003"
    assert order[1] == "TASK-001"


def test_unknown_dependency_rejected():
    tasks = [Task(id="TASK-001", description="x", depends_on=["TASK-999"])]
    with pytest.raises(TaskGraphError):
        topological_order(tasks)


def test_cycle_rejected():
    tasks = [
        Task(id="A", description="x", depends_on=["B"]),
        Task(id="B", description="y", depends_on=["A"]),
    ]
    with pytest.raises(TaskGraphError, match="cycle"):
        topological_order(tasks)


def test_duplicate_ids_rejected():
    tasks = [Task(id="A", description="x"), Task(id="A", description="y")]
    with pytest.raises(TaskGraphError):
        topological_order(tasks)


def test_ready_tasks():
    tasks = _tasks()
    tasks[0].status = TaskStatus.COMPLETED
    assert {t.id for t in ready_tasks(tasks)} == {"TASK-002", "TASK-003"}


def test_skipped_dependency_satisfies():
    tasks = _tasks()
    tasks[0].status = TaskStatus.SKIPPED
    tasks[1].status = TaskStatus.COMPLETED
    tasks[2].status = TaskStatus.COMPLETED
    assert {t.id for t in ready_tasks(tasks)} == {"TASK-004"}


def test_in_progress_not_ready():
    tasks = [Task(id="A", description="x")]
    tasks[0].status = TaskStatus.IN_PROGRESS
    assert ready_tasks(tasks) == []
