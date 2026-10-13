"""Expert Coder agent (spec section 10).

A senior reviewer that improves the Builder's work: diff-first context,
minimal targeted changes, verification through tools.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from forgex.agents.base import BaseAgent, prefetch_files
from forgex.config.schema import ForgexConfig
from forgex.models.router import ModelRouter
from forgex.orchestration.checkpoints import create_checkpoint, find_pre_task_checkpoint
from forgex.orchestration.events import EventRecorder
from forgex.orchestration.stores import ProjectStores
from forgex.research.citations import format_notes
from forgex.sandbox.permissions import permission_set_for
from forgex.schemas.agent import AgentRole, ExpertCoderResult
from forgex.schemas.error import ErrorRecord, ForgexError, ProjectError
from forgex.schemas.event import EventType
from forgex.schemas.plan import ArchitecturePlan
from forgex.schemas.research import ResearchNote
from forgex.schemas.task import Task
from forgex.tools import ToolExecutor, build_tool_registry, create_context
from forgex.tools.git import git_changed_files, git_diff, git_diff_range, is_dirty

logger = logging.getLogger("forgex.agents.expert_coder")

MAX_DIFF_CHARS = 20_000
MAX_PREFETCH_CHARS = 40_000
MAX_PREFETCH_FILES = 12


class ExpertCoderAgent(BaseAgent):
    role = AgentRole.EXPERT_CODER
    prompt_name = "expert_coder"

    def __init__(
        self,
        *,
        router: ModelRouter,
        tools: ToolExecutor,
        events: EventRecorder | None = None,
        run_id: str | None = None,
    ) -> None:
        super().__init__(router=router, events=events, run_id=run_id)
        self._tools = tools

    async def review(
        self,
        *,
        task: Task | None = None,
        plan: ArchitecturePlan | None = None,
        research: list[ResearchNote] | None = None,
        diff: str = "",
        changed_files: list[str] | None = None,
        errors: list[ErrorRecord] | None = None,
        extra_context: str = "",
    ) -> ExpertCoderResult:
        if self._events:
            self._events.record(
                EventType.AGENT_STARTED,
                {"agent": self.role.value, "task": task.id if task else None},
                run_id=self._run_id,
            )

        changed = list(changed_files or [])
        seeds = list(changed)
        try:
            from forgex.context.manager import ContextManager

            manager = ContextManager(self._tools.context.workspace)
            for s in changed:
                for imp in manager.importers_of(s, max_depth=1):
                    if imp not in seeds:
                        seeds.append(imp)
            seeds = seeds[:MAX_PREFETCH_FILES]
        except Exception:
            logger.warning("impact analysis unavailable; changed files only", exc_info=True)

        existing = prefetch_files(
            self._tools.context.workspace,
            seeds,
            budget=MAX_PREFETCH_CHARS,
            max_files=MAX_PREFETCH_FILES,
        )

        parts: list[str] = []
        if task:
            parts.append(
                f"<task>\nID: {task.id}\nDescription: {task.description}\nCriteria: {', '.join(task.acceptance_criteria)}\n</task>"
            )
        if plan:
            parts.append(f"<plan>\nGoal: {plan.goal}\nArchitecture: {plan.architecture}\n</plan>")
        if research:
            parts.append(f"<research>\n{format_notes(research)}\n</research>")
        if errors:
            err_text = "\n".join(f"- [{e.source}] {e.kind}: {e.message}" for e in errors[-5:])
            parts.append(f"<errors>\n{err_text}\n</errors>")
        if extra_context:
            parts.append(extra_context)

        diff_snippet = diff[:MAX_DIFF_CHARS] + ("\n... [diff trimmed]" if len(diff) > MAX_DIFF_CHARS else "")
        parts.append(f"<diff>\n{diff_snippet or '(no diff)'}\n</diff>")
        if existing:
            parts.append(f"<existing_files>\n{existing}\n</existing_files>")

        parts.append(
            "Review the changes above. Refactor, optimize, fix, simplify, and verify with tests. If the code is already solid, change nothing."
        )

        instruction = "\n\n".join(parts)
        loop_res = await self._tool_loop(instruction, self._tools, ExpertCoderResult)
        result: ExpertCoderResult = loop_res.report

        if self._events:
            self._events.record(
                EventType.AGENT_COMPLETED,
                {
                    "agent": self.role.value,
                    "status": result.status,
                    "improvements": len(result.improvements),
                    "changed_files": result.changed_files,
                },
                run_id=self._run_id,
            )
        return result


def build_coder(
    *,
    config: ForgexConfig,
    workspace: Path,
    stores: ProjectStores,
    router: ModelRouter | None = None,
    approval: Callable[[str], bool] | None = None,
    run_id: str | None = None,
) -> ExpertCoderAgent:
    router = router or ModelRouter(config, usage=stores.usage)
    tool_ctx = create_context(
        workspace=workspace,
        config=config,
        events=stores.recorder,
        approval=approval,
        run_id=run_id,
        agent=AgentRole.EXPERT_CODER,
    )
    tools = ToolExecutor(
        registry=build_tool_registry(),
        permissions=permission_set_for(AgentRole.EXPERT_CODER),
        context=tool_ctx,
    )
    return ExpertCoderAgent(
        router=router,
        tools=tools,
        events=stores.recorder,
        run_id=run_id,
    )


def resolve_review_scope(
    *,
    stores: ProjectStores,
    task_id: str | None,
    base_commit: str | None,
) -> tuple[Task | None, str, list[str]] | None:
    task = None
    if task_id is not None:
        tasks = stores.tasks.load()
        task = next((t for t in tasks if t.id == task_id), None)
        if task is None:
            raise ProjectError(f"Unknown task: {task_id}")

    if base_commit is None and task_id is not None and not is_dirty(stores.root):
        record = find_pre_task_checkpoint(task_id, stores=stores)
        if record is not None and record.git_commit:
            base_commit = record.git_commit

    if base_commit:
        diff = git_diff_range(stores.root, base_commit)
        changed = git_changed_files(stores.root, base_commit)
    else:
        diff = git_diff(stores.root)
        changed = git_changed_files(stores.root)

    if not diff and not changed:
        return None
    return task, diff, changed


async def _single_review(
    *,
    stores: ProjectStores,
    config: ForgexConfig,
    task_id: str | None = None,
    base_commit: str | None = None,
    coder: ExpertCoderAgent | None = None,
    approval: Callable[[str], bool] | None = None,
) -> ExpertCoderResult | None:
    state = stores.state.load()
    if state is None:
        raise ProjectError("Project state missing — run `forgex init` first.")

    scope = resolve_review_scope(stores=stores, task_id=task_id, base_commit=base_commit)
    if scope is None:
        return None
    task, diff, changed = scope

    create_checkpoint(
        f"pre-review{'-' + task_id if task_id else ''}",
        stores=stores,
        description="Before expert coder review",
    )

    agent = coder or build_coder(
        config=config,
        workspace=stores.root,
        stores=stores,
        approval=approval,
        run_id=state.current_run_id,
    )
    owns_agent = coder is None
    try:
        result = await agent.review(
            task=task,
            plan=state.architecture_plan,
            research=state.research,
            diff=diff,
            changed_files=changed,
            errors=state.errors[-5:],
        )
    except ForgexError as exc:
        state.errors.append(
            ErrorRecord(
                source="expert_coder",
                kind=type(exc).__name__,
                message=str(exc),
                run_id=state.current_run_id,
            )
        )
        stores.save_state(state)
        raise
    finally:
        if owns_agent:
            await agent.aclose()

    if result.changed_files:
        state.changed_files = sorted(set(state.changed_files) | set(result.changed_files))
        stores.save_state(state)
    return result


async def review_work(
    *,
    stores: ProjectStores,
    config: ForgexConfig,
    task_id: str | None = None,
    base_commit: str | None = None,
    coder: ExpertCoderAgent | None = None,
    approval: Callable[[str], bool] | None = None,
) -> ExpertCoderResult | None:
    if config.ensemble.enabled:
        from forgex.agents.ensemble import ensemble_review

        return await ensemble_review(
            stores=stores,
            config=config,
            task_id=task_id,
            base_commit=base_commit,
            applier=coder,
            approval=approval,
        )
    return await _single_review(
        stores=stores,
        config=config,
        task_id=task_id,
        base_commit=base_commit,
        coder=coder,
        approval=approval,
    )
