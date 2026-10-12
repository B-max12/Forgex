"""Supervisor agent (spec sections 11, 56, 58).

inspect → diagnose → instruct repair.
Verification is deterministic; this agent adds audit judgment;
quality gates enforce that red tests/builds never pass.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from forgex.agents.base import BaseAgent
from forgex.config.schema import ForgexConfig
from forgex.models.router import ModelRouter
from forgex.orchestration.events import EventRecorder
from forgex.orchestration.stores import ProjectStores
from forgex.research.citations import format_notes
from forgex.schemas.agent import (
    AgentRole,
    SupervisorJudgment,
    SupervisorReport,
)
from forgex.schemas.error import ErrorRecord, ProjectError
from forgex.schemas.event import EventType
from forgex.schemas.plan import ArchitecturePlan
from forgex.schemas.research import ResearchNote
from forgex.schemas.result import TestResults, VerificationOutcome
from forgex.schemas.task import Task
from forgex.sandbox.executor import make_executor
from forgex.sandbox.permissions import permission_set_for
from forgex.tools import ToolExecutor, build_tool_registry, create_context
from forgex.tools.git import current_branch, git_log, has_git_repo, is_dirty
from forgex.tools.verification import run_verification

logger = logging.getLogger("forgex.agents.supervisor")


def _git_summary(root: Path) -> str:
    if not has_git_repo(root):
        return "not a git repository"
    branch = current_branch(root) or "unknown"
    dirty = "dirty" if is_dirty(root) else "clean"
    log = git_log(root, limit=5)
    return f"Branch: {branch} ({dirty})\nRecent commits:\n{log}"


def _format_verification(outcome: VerificationOutcome) -> str:
    lines = []
    if outcome.tests:
        t = outcome.tests
        p = t.passed if t.passed is not None else "?"
        f = t.failed if t.failed is not None else "?"
        lines.append(f"Tests: exit={t.exit_code}, passed={p}, failed={f}, timed_out={t.timed_out}")
        if t.output_tail:
            lines.append(f"--- test tail ---\n{t.output_tail[-1500:]}")
    else:
        lines.append("Tests: not detected / not run")

    if outcome.build:
        b = outcome.build
        lines.append(f"Build: exit={b.exit_code}, timed_out={b.timed_out}")
        if not b.ok and b.output_tail:
            lines.append(f"--- build error ---\n{b.output_tail[-1000:]}")

    if outcome.lint:
        ln = outcome.lint
        lines.append(f"Lint: exit={ln.exit_code}")
        if not ln.ok and ln.output_tail:
            lines.append(f"--- lint error ---\n{ln.output_tail[-1000:]}")

    return "\n".join(lines)


def apply_quality_gates(
    judgment: SupervisorJudgment, outcome: VerificationOutcome
) -> SupervisorReport:
    """Compose final report. Gates can only worsen a verdict, never improve it."""
    status = judgment.status
    errors = list(judgment.errors)
    warnings = list(judgment.warnings)
    req_changes = list(judgment.required_changes)

    # 1. Hard gates
    if outcome.tests is not None:
        if (outcome.tests.exit_code is not None and outcome.tests.exit_code not in (0, 5)) or (
            outcome.tests.failed and outcome.tests.failed > 0
        ):
            status = "fail"
            msg = f"tests failed ({outcome.tests.failed or 0} failed, exit {outcome.tests.exit_code})"
            if msg not in errors:
                errors.append(msg)
            if not req_changes:
                req_changes.append("Fix the failing test suite")
        if outcome.tests.timed_out:
            status = "fail"
            if "tests timed out" not in errors:
                errors.append("tests timed out")

    if outcome.build is not None and not outcome.build.ok:
        status = "fail"
        msg = f"build failed (exit {outcome.build.exit_code})"
        if msg not in errors:
            errors.append(msg)
        if not req_changes:
            req_changes.append("Fix build failures")

    if outcome.lint is not None and not outcome.lint.ok:
        status = "fail"
        msg = f"lint failed (exit {outcome.lint.exit_code})"
        if msg not in errors:
            errors.append(msg)

    # 2. Soft gates (floor at needs_review)
    if outcome.tests is None:
        warnings.append("no test suite detected")
        if status == "pass":
            status = "needs_review"
    elif outcome.tests.exit_code == 5:
        warnings.append("pytest collected 0 tests")
        if status == "pass":
            status = "needs_review"
    elif outcome.tests.exit_code is None:
        warnings.append("test command was not executed")
        if not any("tests failed" in e for e in errors):
            errors.append("tests failed: command denied")
        status = "needs_review"

    # 3. Model verdict preservation
    if judgment.status in ("fail", "needs_review"):
        status = judgment.status

    return SupervisorReport(
        status=status,
        summary=judgment.summary,
        errors=errors,
        warnings=warnings,
        required_changes=req_changes,
        recommended_changes=judgment.recommended_changes,
        tests=outcome.tests,
        build=outcome.build,
        lint=outcome.lint,
    )


class SupervisorAgent(BaseAgent):
    role = AgentRole.SUPERVISOR
    prompt_name = "supervisor"

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

    async def audit(
        self,
        *,
        request: str,
        plan: ArchitecturePlan | None,
        tasks: list[Task],
        verification: VerificationOutcome,
        research: list[ResearchNote] | None = None,
        errors: list[ErrorRecord] | None = None,
    ) -> SupervisorJudgment:
        if self._events:
            self._events.record(
                EventType.AGENT_STARTED,
                {"agent": self.role.value},
                run_id=self._run_id,
            )

        v_text = _format_verification(verification)
        git_text = _git_summary(self._tools.context.workspace)
        research_text = format_notes(research or [])

        tasks_summary = "\n".join(
            f"- [{t.status.value}] {t.id}: {t.description} (attempts: {t.attempts})"
            for t in tasks
        )
        err_text = "\n".join(f"- [{e.source}] {e.kind}: {e.message}" for e in (errors or [])[-5:])

        instruction = (
            f"<user_request>\n{request}\n</user_request>\n\n"
            f"<plan>\nGoal: {plan.goal if plan else 'none'}\nCriteria: {', '.join(plan.acceptance_criteria) if plan else 'none'}\n</plan>\n\n"
            f"<tasks>\n{tasks_summary}\n</tasks>\n\n"
            f"<verification>\n{v_text}\n</verification>\n\n"
            f"<git>\n{git_text}\n</git>\n\n"
            f"<research>\n{research_text}\n</research>\n\n"
            f"<errors>\n{err_text or '(no errors recorded)'}\n</errors>\n\n"
            "Audit the repository. Use tools to inspect code if needed. Return your decisive verdict (pass/fail/needs_review)."
        )

        loop_res = await self._tool_loop(instruction, self._tools, SupervisorJudgment)
        result: SupervisorJudgment = loop_res.report

        if self._events:
            self._events.record(
                EventType.AGENT_COMPLETED,
                {
                    "agent": self.role.value,
                    "status": result.status,
                    "errors": len(result.errors),
                    "required_changes": len(result.required_changes),
                },
                run_id=self._run_id,
            )
        return result


def build_supervisor(
    *,
    config: ForgexConfig,
    workspace: Path,
    stores: ProjectStores,
    router: ModelRouter | None = None,
    approval: Callable[[str], bool] | None = None,
    run_id: str | None = None,
) -> SupervisorAgent:
    router = router or ModelRouter(config, usage=stores.usage)
    tool_ctx = create_context(
        workspace=workspace,
        config=config,
        events=stores.recorder,
        approval=approval,
        run_id=run_id,
        agent=AgentRole.SUPERVISOR,
    )
    tools = ToolExecutor(
        registry=build_tool_registry(),
        permissions=permission_set_for(AgentRole.SUPERVISOR),
        context=tool_ctx,
    )
    return SupervisorAgent(
        router=router,
        tools=tools,
        events=stores.recorder,
        run_id=run_id,
    )


async def supervise(
    *,
    stores: ProjectStores,
    config: ForgexConfig,
    approval: Callable[[str], bool] | None = None,
    include_build: bool = True,
    include_lint: bool = True,
    supervisor: SupervisorAgent | None = None,
) -> SupervisorReport:
    state = stores.state.load()
    if state is None:
        raise ProjectError("Project state missing — run `forgex init` first.")

    agent = supervisor or build_supervisor(
        config=config,
        workspace=stores.root,
        stores=stores,
        approval=approval,
        run_id=state.current_run_id,
    )
    owns_agent = supervisor is None

    exec_inst = getattr(getattr(getattr(agent, "_tools", None), "context", None), "executor", None)
    if exec_inst is None:
        exec_inst = make_executor(stores.root, approval=approval)

    outcome = await run_verification(
        root=stores.root,
        executor=exec_inst,
        events=stores.recorder,
        run_id=state.current_run_id,
        include_build=include_build,
        include_lint=include_lint,
    )

    try:
        judgment = await agent.audit(
            request=state.user_request or "",
            plan=state.architecture_plan,
            tasks=stores.tasks.load(),
            verification=outcome,
            research=state.research,
            errors=state.errors,
        )
    finally:
        if owns_agent:
            await agent.aclose()

    report = apply_quality_gates(judgment, outcome)

    state.test_results = outcome.tests
    state.build_results = outcome.build
    state.last_supervisor_status = report.status
    stores.save_state(state)

    return report
