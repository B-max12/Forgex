"""Agent identity, roles, and agent output schemas."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from forgex.schemas.plan import ArchitectResult as ArchitectResult


class AgentRole(str, Enum):
    ARCHITECT = "architect"
    BUILDER = "builder"
    EXPERT_CODER = "expert_coder"
    SUPERVISOR = "supervisor"

    @property
    def display_name(self) -> str:
        return self.value.replace("_", " ").title()


class BuilderResult(BaseModel):
    """The Builder's structured self-report after executing one task (§9).

    NOTE: 'completed' is the Builder's own claim — independent verification
    is the Supervisor's responsibility (Phase 8) and the repair loop (Phase 9).
    """

    model_config = ConfigDict(extra="ignore")

    status: Literal["completed", "failed"]
    summary: str = ""
    changed_files: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)


class ExpertCoderResult(BaseModel):
    """The Expert Coder's structured review report (spec section 10).

    Empty changed_files is a valid outcome: 'reviewed, nothing warranted
    changes'. unfixed_issues are handed forward to the Supervisor (Phase 8).
    """

    model_config = ConfigDict(extra="ignore")

    status: Literal["completed", "failed"]
    summary: str = ""
    changed_files: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
    issues_found: list[str] = Field(default_factory=list)
    unfixed_issues: list[str] = Field(default_factory=list)


class ReviewFinding(BaseModel):
    """One issue found by an ensemble reviewer (spec section 15)."""

    model_config = ConfigDict(extra="ignore")

    issue: str
    severity: Literal["critical", "major", "minor"] = "major"
    file: str | None = None
    suggestion: str | None = None


class ReviewFindings(BaseModel):
    """One reviewer's read-only verdict on a diff."""

    model_config = ConfigDict(extra="ignore")

    verdict: Literal["ok", "needs_changes"]
    summary: str = ""
    findings: list[ReviewFinding] = Field(default_factory=list)


class SupervisorJudgment(BaseModel):
    """The LLM Supervisor's verdict (spec section 11 output)."""

    model_config = ConfigDict(extra="ignore")

    status: Literal["pass", "fail", "needs_review"]
    summary: str = ""
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    required_changes: list[str] = Field(default_factory=list)
    recommended_changes: list[str] = Field(default_factory=list)


class SupervisorReport(BaseModel):
    """Final supervisor verdict: LLM judgment + deterministic quality gates.

    Gates can only WORSEN a verdict, never improve it (spec sections 56, 58):
    a red test suite forces 'fail' regardless of the model's opinion."""

    model_config = ConfigDict(extra="ignore")

    status: Literal["pass", "fail", "needs_review"]
    summary: str = ""
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    required_changes: list[str] = Field(default_factory=list)
    recommended_changes: list[str] = Field(default_factory=list)
    tests: Any | None = None
    build: Any | None = None
    lint: Any | None = None


SupervisorReport.model_rebuild()
