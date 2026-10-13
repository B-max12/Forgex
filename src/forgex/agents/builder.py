"""Builder agent (spec section 9).

Receives task, plan, and research; implements task through the
permission-gated tool loop; reports changed files.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from forgex.agents.base import BaseAgent, prefetch_files
from forgex.config.schema import ForgexConfig
from forgex.models.router import ModelRouter
from forgex.orchestration.checkpoints import create_checkpoint
from forgex.orchestration.events import EventRecorder
from forgex.orchestration.stores import ProjectStores
from forgex.research.citations import format_notes
from forgex.sandbox.permissions import permission_set_for
from forgex.schemas.agent import AgentRole, BuilderResult
from forgex.schemas.error import ErrorRecord, ProjectError
from forgex.schemas.event import EventType
from forgex.schemas.plan import ArchitecturePlan
from forgex.schemas.research import ResearchNote
from forgex.schemas.task import Task, TaskStatus
from forgex.tools import ToolExecutor, build_tool_registry, create_context

logger = logging.getLogger("forgex.agents.builder")

MAX_PREFETCH_CHARS = 30_000


class BuilderAgent(BaseAgent):
    role = AgentRole.BUILDER
    prompt_name = "builder"

    def __init__(
        self,
        *,
        router: ModelRouter,
        tools: ToolExecutor,
        events: EventRecorder | None = None,
        run_id: str | None = None,
        max_prefetch_chars: int = MAX_PREFETCH_CHARS,
    ) -> None:
        super().__init__(router=router, events=events, run_id=run_id)
        self._tools = tools
        self._max_prefetch_chars = max_prefetch_chars

    def _prefetch_existing(self, task: Task) -> str:
        workspace = self._tools.context.workspace
        planned = prefetch_files(workspace, task.files, budget=self._max_prefetch_chars)
        remaining = self._max_prefetch_chars - len(planned)
        if remaining <= 0:
            return planned
        extra = self._related_context(
            workspace,
            query=task.description,
            seeds=list(task.files),
            budget=remaining,
            exclude=set(task.files),
        )
        return planned + ("\n\n" + extra if extra else "")

    def _related_context(
        self,
        workspace: Path,
        *,
        query: str,
        seeds: list[str],
        budget: int,
        exclude: set[str],
    ) -> str:
        try:
            from forgex.context.manager import ContextManager

            bundle = ContextManager(workspace).build_context(
                query=query,
                seeds=seeds,
                budget=budget,
                max_files=4,
                exclude=exclude,
            )
            return bundle.render()
        except Exception:
            logger.warning("context retrieval failed; planned files only", exc_info=True)
            return ""

    async def execute(
        self,
        task: Task,
        *,
        plan: ArchitecturePlan | None = None,
        research: list[ResearchNote] | None = None,
    ) -> BuilderResult:
        if self._events:
            self._events.record(
                EventType.AGENT_STARTED,
                {"agent": self.role.value, "task": task.id},
                run_id=self._run_id,
            )

        existing = self._prefetch_existing(task)
        research_text = format_notes(research or [])

        instruction = (
            f"<task>\nID: {task.id}\nDescription: {task.description}\n"
            f"Files: {', '.join(task.files) or 'none specified'}\n"
            f"Acceptance Criteria: {', '.join(task.acceptance_criteria) or 'none'}\n</task>\n\n"
            f"<plan>\nGoal: {plan.goal if plan else ''}\nArchitecture: {plan.architecture if plan else ''}\n</plan>\n\n"
            f"<research>\n{research_text}\n</research>\n\n"
            f"<existing_files>\n{existing or '(none found)'}\n</existing_files>\n\n"
            "Implement this task using the tools. Inspect files first, make minimal targeted edits, and validate your work before reporting done."
        )

        loop_res = await self._tool_loop(instruction, self._tools, BuilderResult)
        result: BuilderResult = loop_res.report

        if self._events:
            self._events.record(
                EventType.AGENT_COMPLETED,
                {
                    "agent": self.role.value,
                    "task": task.id,
                    "status": result.status,
                    "changed_files": result.changed_files,
                },
                run_id=self._run_id,
            )
        return result


def build_builder(
    *,
    config: ForgexConfig,
    workspace: Path,
    stores: ProjectStores,
    router: ModelRouter | None = None,
    approval: Callable[[str], bool] | None = None,
    run_id: str | None = None,
) -> BuilderAgent:
    router = router or ModelRouter(config, usage=stores.usage)
    tool_ctx = create_context(
        workspace=workspace,
        config=config,
        events=stores.recorder,
        approval=approval,
        run_id=run_id,
        agent=AgentRole.BUILDER,
    )
    tools = ToolExecutor(
        registry=build_tool_registry(),
        permissions=permission_set_for(AgentRole.BUILDER),
        context=tool_ctx,
    )
    return BuilderAgent(
        router=router,
        tools=tools,
        events=stores.recorder,
        run_id=run_id,
    )


async def execute_task(
    task: Task,
    *,
    builder: BuilderAgent,
    stores: ProjectStores,
    config: ForgexConfig,
    plan: ArchitecturePlan | None = None,
    research: list[ResearchNote] | None = None,
) -> BuilderResult:
    state = stores.state.load()
    if state is None:
        raise ProjectError("Project state missing — run `forgex init` first.")

    effective_plan = plan or state.architecture_plan

    tasks = stores.tasks.load()
    task_map = {t.id: t for t in tasks}
    if task.id in task_map:
        task = task_map[task.id]

    # Verify dependencies
    for dep_id in task.depends_on:
        dep = task_map.get(dep_id)
        if not dep or dep.status not in (TaskStatus.COMPLETED, TaskStatus.SKIPPED):
            raise ProjectError(f"Dependency {dep_id} for {task.id} is not satisfied")

    # Mark IN_PROGRESS
    task.status = TaskStatus.IN_PROGRESS
    task.attempts += 1
    task.updated_at = datetime.now(UTC)
    state.current_task = task.id
    state.current_agent = AgentRole.BUILDER
    stores.save_tasks(tasks, project_id=state.project_id)
    stores.save_state(state)

    create_checkpoint(
        f"pre-{task.id}",
        stores=stores,
        description=f"Before executing {task.id}",
        run_id=state.current_run_id,
    )

    stores.recorder.record(
        EventType.TASK_STARTED,
        {"task": task.id, "attempt": task.attempts},
        run_id=state.current_run_id,
    )

    try:
        result = await builder.execute(task, plan=effective_plan, research=research)
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        task.status = TaskStatus.FAILED
        task.result = f"builder error: {exc}"
        task.updated_at = datetime.now(UTC)
        if task.id not in state.failed_tasks:
            state.failed_tasks.append(task.id)
        state.errors.append(
            ErrorRecord(
                source="builder",
                kind=type(exc).__name__,
                message=str(exc),
                run_id=state.current_run_id,
            )
        )
        state.current_task = None
        state.current_agent = None
        stores.save_tasks(tasks, project_id=state.project_id)
        stores.save_state(state)
        stores.recorder.record(
            EventType.TASK_COMPLETED,
            {"task": task.id, "status": "failed", "error": str(exc)},
            run_id=state.current_run_id,
        )
        raise

    if result.status == "completed":
        task.status = TaskStatus.COMPLETED
        if task.id not in state.completed_tasks:
            state.completed_tasks.append(task.id)
        if task.id in state.failed_tasks:
            state.failed_tasks.remove(task.id)
    else:
        task.status = TaskStatus.FAILED
        if task.id not in state.failed_tasks:
            state.failed_tasks.append(task.id)

    task.result = result.summary
    task.updated_at = datetime.now(UTC)
    if result.changed_files:
        state.changed_files = sorted(set(state.changed_files) | set(result.changed_files))

    state.current_task = None
    state.current_agent = None
    stores.save_tasks(tasks, project_id=state.project_id)
    stores.save_state(state)

    stores.recorder.record(
        EventType.TASK_COMPLETED,
        {"task": task.id, "status": task.status.value, "changed_files": result.changed_files},
        run_id=state.current_run_id,
    )
    return result
