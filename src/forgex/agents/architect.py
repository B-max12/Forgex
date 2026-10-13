"""Architect agent (spec section 7).

Understand → Analyze → Decompose → Research → Plan → Validate.
Never writes code: read-only tools, official registry research,
structured plan output, dependency graph validation.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from forgex.agents.base import BaseAgent
from forgex.config.schema import ForgexConfig
from forgex.models.base import Message
from forgex.models.router import ModelRouter
from forgex.orchestration.events import EventRecorder
from forgex.orchestration.stores import ProjectStores
from forgex.orchestration.workflow import transition
from forgex.research.citations import format_notes
from forgex.research.engine import ResearchEngine
from forgex.sandbox.permissions import permission_set_for
from forgex.schemas.agent import AgentRole
from forgex.schemas.error import AgentOutputError, ProjectError
from forgex.schemas.event import EventType
from forgex.schemas.plan import (
    AnalysisResult,
    ArchitectResult,
    ArchitecturePlan,
    specs_to_tasks,
)
from forgex.schemas.project import WorkflowStatus
from forgex.schemas.task import topological_order
from forgex.tools import ToolCall, ToolExecutor, build_tool_registry, create_context

logger = logging.getLogger("forgex.agents.architect")


class ArchitectAgent(BaseAgent):
    role = AgentRole.ARCHITECT
    prompt_name = "architect"

    def __init__(
        self,
        *,
        router: ModelRouter,
        tools: ToolExecutor,
        research: ResearchEngine,
        events: EventRecorder | None = None,
        run_id: str | None = None,
    ) -> None:
        super().__init__(router=router, events=events, run_id=run_id)
        self._tools = tools
        self._research = research

    async def _gather_context(self) -> str:
        info_res = await self._tools.execute(ToolCall(name="project_info", arguments={}))
        files_res = await self._tools.execute(ToolCall(name="list_files", arguments={}))

        brief = f"Repository Overview:\n{info_res.output}\n\nFiles:\n{files_res.output}"
        try:
            from forgex.context.manager import ContextManager

            symbols = ContextManager(self._tools.context.workspace).symbol_map()
            if symbols:
                brief += "\n\nSymbols:\n" + symbols
        except Exception:
            logger.warning("symbol map unavailable", exc_info=True)
        if len(brief) > 16_000:
            brief = brief[:16_000] + "\n... [context truncated to stay within token budget]"
        return brief

    async def plan(
        self,
        user_request: str,
        *,
        on_stage: Callable[[str], None] | None = None,
    ) -> ArchitectResult:
        if self._events:
            self._events.record(
                EventType.AGENT_STARTED,
                {"agent": self.role.value, "request": user_request},
                run_id=self._run_id,
            )

        repo_context = await self._gather_context()

        # Stage 1: Analysis & research topic selection
        if on_stage:
            on_stage("analyzing")

        stage1_msg = (
            f"<user_request>\n{user_request}\n</user_request>\n\n"
            f"<repository>\n{repo_context}\n</repository>\n\n"
            "Analyze this request and repository. State the goal, requirements, candidate libraries, and research topics."
        )
        analysis: AnalysisResult = await self._generate_structured(
            [Message(role="user", content=stage1_msg)], AnalysisResult
        )

        # Stage 2: Dependency research
        if on_stage:
            on_stage("researching")
        notes = await self._research.research(analysis.research_topics)
        if self._events:
            self._events.record(
                EventType.RESEARCH_COMPLETED,
                {"topics": [n.topic for n in notes], "available": sum(1 for n in notes if n.available)},
                run_id=self._run_id,
            )

        # Stage 3: Architecture plan creation
        if on_stage:
            on_stage("planning")

        research_text = format_notes(notes)
        stage2_msg = (
            f"<user_request>\n{user_request}\n</user_request>\n\n"
            f"<repository>\n{repo_context}\n</repository>\n\n"
            f"<analysis>\nGoal: {analysis.goal}\nRequirements: {', '.join(analysis.requirements)}\nCandidate Libraries: {', '.join(analysis.candidate_libraries)}\n</analysis>\n\n"
            f"<research>\n{research_text}\n</research>\n\n"
            "Produce the final implementation plan adhering to the JSON schema. Decompose into focused, verifiable tasks."
        )

        plan: ArchitecturePlan = await self._generate_structured(
            [Message(role="user", content=stage2_msg)], ArchitecturePlan
        )

        # Validate plan
        if not plan.tasks:
            raise AgentOutputError("Architect produced an empty plan (no tasks)")

        # Validate graph: cycle detection, unknown deps, duplicate IDs
        runtime_tasks = specs_to_tasks(plan.tasks)
        topological_order(runtime_tasks)

        result = ArchitectResult(plan=plan, research=notes, analysis=analysis)
        if self._events:
            self._events.record(
                EventType.AGENT_COMPLETED,
                {"agent": self.role.value, "tasks": len(plan.tasks)},
                run_id=self._run_id,
            )
        return result

    async def aclose(self) -> None:
        await super().aclose()
        await self._research.aclose()


def build_planner(
    *,
    config: ForgexConfig,
    workspace: Path,
    stores: ProjectStores,
    router: ModelRouter | None = None,
    run_id: str | None = None,
) -> ArchitectAgent:
    router = router or ModelRouter(config, usage=stores.usage)
    tool_ctx = create_context(
        workspace=workspace,
        config=config,
        events=stores.recorder,
        run_id=run_id,
        agent=AgentRole.ARCHITECT,
    )
    tools = ToolExecutor(
        registry=build_tool_registry(),
        permissions=permission_set_for(AgentRole.ARCHITECT),
        context=tool_ctx,
    )
    research = ResearchEngine(config=config)
    return ArchitectAgent(
        router=router,
        tools=tools,
        research=research,
        events=stores.recorder,
        run_id=run_id,
    )


async def plan_project(
    planner: ArchitectAgent,
    *,
    stores: ProjectStores,
    request: str,
    dry_run: bool = False,
    progress: Callable[[str], None] | None = None,
) -> ArchitectResult:
    state = stores.state.load()
    if state is None:
        raise ProjectError("Project state missing — run `forgex init` first.")

    # Reset if from completed/failed
    if state.status in (WorkflowStatus.COMPLETED, WorkflowStatus.FAILED, WorkflowStatus.CANCELLED):
        state.status = WorkflowStatus.INITIALIZING

    if state.status == WorkflowStatus.PLANNING or state.status == WorkflowStatus.INITIALIZING:
        state.status = transition(state.status, WorkflowStatus.ANALYZING)

    if not dry_run:
        state.user_request = request
        stores.save_state(state)

    def on_stage(stage: str) -> None:
        if progress:
            progress(stage)
        if not dry_run:
            if stage == "researching" and state.status == WorkflowStatus.ANALYZING:
                state.status = transition(state.status, WorkflowStatus.RESEARCHING)
                stores.save_state(state)
            elif stage == "planning" and state.status in (WorkflowStatus.RESEARCHING, WorkflowStatus.ANALYZING):
                state.status = transition(state.status, WorkflowStatus.PLANNING)
                stores.save_state(state)

    result = await planner.plan(request, on_stage=on_stage)

    if not dry_run:
        state.status = WorkflowStatus.PLANNING
        state.architecture_plan = result.plan
        state.research = result.research
        tasks = specs_to_tasks(result.plan.tasks)
        state.tasks = [t.id for t in tasks]
        state.completed_tasks = []
        state.failed_tasks = []
        stores.save_tasks(tasks, project_id=state.project_id)
        stores.save_state(state)
        stores.recorder.record(
            EventType.PLAN_CREATED,
            {"goal": result.plan.goal, "tasks": len(result.plan.tasks)},
            run_id=state.current_run_id,
        )

    return result
