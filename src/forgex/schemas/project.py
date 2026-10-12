"""Project and run state (spec sections 5, 53).

ProjectState is THE central shared object: agents read and write
structured state instead of giant conversations (spec section 2.7).
WorkflowStatus is the phase machine from spec section 53; the transition
RULES live in forgex.orchestration.workflow.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from forgex.schemas.agent import AgentRole
from forgex.schemas.error import ErrorRecord
from forgex.schemas.plan import ArchitecturePlan
from forgex.schemas.research import ResearchNote
from forgex.schemas.result import BuildResults, TestResults


class WorkflowStatus(str, Enum):
    INITIALIZING = "initializing"
    ANALYZING = "analyzing"
    RESEARCHING = "researching"
    PLANNING = "planning"
    BUILDING = "building"
    REVIEWING = "reviewing"
    TESTING = "testing"
    SUPERVISING = "supervising"
    REPAIRING = "repairing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunState(BaseModel):
    """Execution run record persisted to database."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    project_id: str
    request: str
    status: RunStatus = RunStatus.RUNNING
    phase: WorkflowStatus = WorkflowStatus.INITIALIZING
    iteration: int = 0
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    summary: str | None = None
    error: str | None = None


class ProjectState(BaseModel):
    """Durable project state, persisted to .forgex/state.json (spec section 5)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    project_id: str
    project_path: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    user_request: str | None = None
    status: WorkflowStatus = WorkflowStatus.INITIALIZING
    iteration: int = 0
    current_run_id: str | None = None
    current_agent: AgentRole | None = None
    current_task: str | None = None
    git_commit: str | None = None

    architecture_plan: ArchitecturePlan | None = None
    research: list[ResearchNote] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)
    tasks: list[str] = Field(default_factory=list)
    completed_tasks: list[str] = Field(default_factory=list)
    failed_tasks: list[str] = Field(default_factory=list)
    errors: list[ErrorRecord] = Field(default_factory=list)

    test_results: TestResults | None = None
    build_results: BuildResults | None = None
    last_supervisor_status: Literal["pass", "fail", "needs_review"] | None = None
