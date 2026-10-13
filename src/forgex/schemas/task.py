"""Task system (spec section 54).

Tasks support dependency ordering, priority, attempts, per-task files
and acceptance criteria. The graph operations (topological order,
readiness, cycle detection) live here so every consumer — engine, CLI,
tests — shares one implementation.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from forgex.schemas.error import TaskGraphError


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class TaskPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


_PRIORITY_RANK = {
    TaskPriority.LOW: 0,
    TaskPriority.MEDIUM: 1,
    TaskPriority.HIGH: 2,
    TaskPriority.CRITICAL: 3,
}


class Task(BaseModel):
    """A single unit of work produced by the Architect, executed by the Builder."""

    model_config = ConfigDict(extra="forbid")

    id: str  # e.g. "TASK-004"
    description: str
    priority: TaskPriority = TaskPriority.MEDIUM
    status: TaskStatus = TaskStatus.PENDING
    depends_on: list[str] = Field(default_factory=list)
    files: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    attempts: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    result: str | None = None


def topological_order(tasks: list[Task]) -> list[Task]:
    """Return tasks in topological order, with priority breaking ties among ready tasks.

    Raises TaskGraphError on duplicate IDs, unknown dependencies, or cycles.
    """
    task_map: dict[str, Task] = {}
    for task in tasks:
        if task.id in task_map:
            raise TaskGraphError(f"Duplicate task ID: {task.id}")
        task_map[task.id] = task

    in_degree: dict[str, int] = {t.id: 0 for t in tasks}
    dependents: dict[str, list[str]] = defaultdict(list)

    for task in tasks:
        for dep in task.depends_on:
            if dep not in task_map:
                raise TaskGraphError(f"Task {task.id} depends on unknown task: {dep}")
            dependents[dep].append(task.id)
            in_degree[task.id] += 1

    # Ready heap or list sorted by priority descending
    ready: list[str] = [t.id for t in tasks if in_degree[t.id] == 0]
    ready.sort(key=lambda tid: (-_PRIORITY_RANK[task_map[tid].priority], tid))

    ordered: list[Task] = []

    while ready:
        curr_id = ready.pop(0)
        ordered.append(task_map[curr_id])

        newly_ready: list[str] = []
        for dep_id in dependents[curr_id]:
            in_degree[dep_id] -= 1
            if in_degree[dep_id] == 0:
                newly_ready.append(dep_id)

        if newly_ready:
            ready.extend(newly_ready)
            ready.sort(key=lambda tid: (-_PRIORITY_RANK[task_map[tid].priority], tid))

    if len(ordered) != len(tasks):
        raise TaskGraphError("Dependency cycle detected in tasks")

    return ordered


def ready_tasks(tasks: list[Task]) -> list[Task]:
    """Return list of tasks that are PENDING and whose dependencies are COMPLETED or SKIPPED."""
    completed_or_skipped = {
        t.id for t in tasks if t.status in (TaskStatus.COMPLETED, TaskStatus.SKIPPED)
    }

    ready = []
    for t in tasks:
        if t.status == TaskStatus.PENDING and all(dep in completed_or_skipped for dep in t.depends_on):
            ready.append(t)
    return ready
