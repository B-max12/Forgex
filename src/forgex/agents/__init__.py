"""Agent package (spec sections 7, 9, 10, 11, 12, 15)."""

from forgex.agents.architect import ArchitectAgent, build_planner, plan_project
from forgex.agents.base import BaseAgent, ToolLoopResult, extract_json, prefetch_files
from forgex.agents.builder import BuilderAgent, build_builder, execute_task
from forgex.agents.ensemble import ReviewerAgent, ensemble_review, synthesize
from forgex.agents.expert_coder import ExpertCoderAgent, build_coder, review_work
from forgex.agents.supervisor import (
    SupervisorAgent,
    apply_quality_gates,
    build_supervisor,
    supervise,
)

__all__ = [
    "ArchitectAgent",
    "BaseAgent",
    "BuilderAgent",
    "ExpertCoderAgent",
    "ReviewerAgent",
    "SupervisorAgent",
    "ToolLoopResult",
    "apply_quality_gates",
    "build_builder",
    "build_coder",
    "build_planner",
    "build_supervisor",
    "ensemble_review",
    "execute_task",
    "extract_json",
    "plan_project",
    "prefetch_files",
    "review_work",
    "supervise",
    "synthesize",
]
