"""Planning schemas (spec sections 7, 8, 54).

The Architect's structured outputs. `AnalysisResult` is the early
understanding pass; `ArchitecturePlan` is the final plan persisted to
state.json. `TaskSpec` is the plan-side task; `specs_to_tasks()` converts
specs into runtime Task objects for the task store.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from forgex.schemas.research import ResearchNote
from forgex.schemas.task import Task, TaskPriority


class TaskSpec(BaseModel):
    """A task as planned by the Architect (no runtime state)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    description: str
    priority: TaskPriority = TaskPriority.MEDIUM
    depends_on: list[str] = Field(default_factory=list)
    files: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    """Stage 1: the Architect's understanding before research."""

    model_config = ConfigDict(extra="forbid")

    goal: str
    requirements: list[str] = Field(default_factory=list)
    candidate_libraries: list[str] = Field(default_factory=list)
    research_topics: list[str] = Field(default_factory=list)


class ArchitecturePlan(BaseModel):
    """Stage 2: the final implementation plan (spec section 7)."""

    model_config = ConfigDict(extra="forbid")

    goal: str
    requirements: list[str] = Field(default_factory=list)
    tasks: list[TaskSpec] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)  # external systems/services
    libraries: list[str] = Field(default_factory=list)  # language packages
    architecture: dict[str, Any] = Field(default_factory=dict)
    risks: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    test_strategy: list[str] = Field(default_factory=list)


class ArchitectResult(BaseModel):
    """Everything the Architect produces in one planning run."""

    plan: ArchitecturePlan
    research: list[ResearchNote] = Field(default_factory=list)
    analysis: AnalysisResult | None = None
    prompt_version: str = "architect:v1"


def specs_to_tasks(specs: list[TaskSpec]) -> list[Task]:
    """Convert planned task specs into runtime Task objects (pending, attempt 0)."""
    now = datetime.now(UTC)
    return [
        Task(
            id=spec.id,
            description=spec.description,
            priority=spec.priority,
            depends_on=list(spec.depends_on),
            files=list(spec.files),
            acceptance_criteria=list(spec.acceptance_criteria),
            created_at=now,
            updated_at=now,
        )
        for spec in specs
    ]
