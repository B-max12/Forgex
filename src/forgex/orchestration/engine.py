"""FORGEX build engine (spec sections 1, 12, 34, 35, 36, 53, 57, 58).

Connects planning, per-task Builder + review, verification, supervision,
and the bounded self-healing repair loop.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from forgex.agents.architect import build_planner, plan_project
from forgex.agents.builder import build_builder, execute_task
from forgex.agents.expert_coder import build_coder, review_work
from forgex.agents.supervisor import build_supervisor, supervise
from forgex.models.router import ModelRouter
from forgex.orchestration.checkpoints import create_checkpoint, latest_checkpoint
from forgex.orchestration.lockfile import RunLock
from forgex.orchestration.stores import ProjectStores
from forgex.orchestration.workflow import transition
from forgex.schemas.agent import SupervisorReport
from forgex.schemas.error import ForgexError, ProjectError, WorkflowError
from forgex.schemas.event import EventType
from forgex.schemas.project import ProjectState, RunState, RunStatus, WorkflowStatus
from forgex.schemas.result import TestResults
from forgex.schemas.task import Task, TaskPriority, TaskStatus, ready_tasks
from forgex.tools.git import git_changed_files, git_diff
from forgex.tools.testing import detect_test_command
from forgex.tools.verification import detect_build_command

logger = logging.getLogger("forgex.engine")

ProgressFn = Callable[[str], None]


class BuildRunResult(BaseModel):
    """Outcome of one build run (rendered per spec sections 57/58)."""

    status: Literal["completed", "failed"]
    verdict: Literal["pass", "fail", "needs_review"] | None = None
    reason: str = ""
    tasks_total: int = 0
    tasks_completed: int = 0
    remaining_tasks: list[str] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)
    tests: TestResults | None = None
    build_ok: bool | None = None
    iterations: int = 0
    checkpoint: str | None = None
    warnings: list[str] = Field(default_factory=list)
    usage: dict[str, Any] | None = None


class DryRunReport(BaseModel):
    planned_tasks: list[dict[str, Any]] = Field(default_factory=list)
    planned_files: list[str] = Field(default_factory=list)
    libraries: list[str] = Field(default_factory=list)
    detected_tests: list[str] | None = None
    detected_build: list[str] | None = None
    agent_sequence: list[str] = Field(default_factory=list)
    max_iterations: int = 5


class BuildEngine:
    def __init__(
        self,
        *,
        stores: ProjectStores,
        config: Any,
        approval: Callable[[str], bool] | None = None,
        progress: ProgressFn | None = None,
        agents: dict[str, Any] | None = None,
        max_iterations: int | None = None,
    ) -> None:
        self._stores = stores
        self._config = config
        self._approval = approval
        self._progress_cb = progress
        self._fakes = agents or {}
        self._max_iterations = (
            max_iterations
            if max_iterations is not None
            else getattr(getattr(config, "workflow", None), "max_iterations", 5)
        )
        self._router: ModelRouter | None = None
        self._run: RunState | None = None
        self._resuming: bool = False

    def _progress(self, msg: str) -> None:
        if self._progress_cb:
            self._progress_cb(msg)

    def _state(self) -> ProjectState:
        st = self._stores.state.load()
        if st is None:
            raise ProjectError("Project is not initialized — run `forgex init` first.")
        return st

    async def _ensure_agents(self) -> None:
        if self._router is None:
            self._router = ModelRouter(self._config, usage=self._stores.usage)

    async def _cleanup(self) -> None:
        if self._router:
            await self._router.aclose()
            self._router = None

    def _incomplete_tasks(self) -> list[str]:
        tasks = self._stores.tasks.load()
        # Non-repair incomplete tasks
        return [
            t.id
            for t in tasks
            if not t.id.startswith("REPAIR-") and t.status != TaskStatus.COMPLETED
        ]

    async def _ensure_plan(self, request: str | None) -> None:
        state = self._state()
        if state.architecture_plan is not None and not request:
            return

        effective_request = request or state.user_request
        if not effective_request:
            raise ProjectError("No user request provided and no plan exists. Specify a request.")

        self._progress("Architect: analyzing and creating implementation plan...")
        state.status = transition(state.status, WorkflowStatus.ANALYZING)
        self._stores.save_state(state)

        planner = self._fakes.get("planner") or build_planner(
            config=self._config,
            workspace=self._stores.root,
            stores=self._stores,
            router=self._router,
            run_id=self._run.run_id if self._run else None,
        )

        res = await plan_project(
            planner,
            stores=self._stores,
            request=effective_request,
            dry_run=False,
            progress=self._progress,
        )
        self._progress(f"Plan created: {len(res.plan.tasks)} tasks.")

    async def _task_loop(self) -> None:
        builder = self._fakes.get("builder") or build_builder(
            config=self._config,
            workspace=self._stores.root,
            stores=self._stores,
            router=self._router,
            approval=self._approval,
            run_id=self._run.run_id if self._run else None,
        )
        coder = self._fakes.get("coder") or build_coder(
            config=self._config,
            workspace=self._stores.root,
            stores=self._stores,
            router=self._router,
            approval=self._approval,
            run_id=self._run.run_id if self._run else None,
        )

        while True:
            tasks = self._stores.tasks.load()
            ready = ready_tasks(tasks)
            # Exclude repair tasks from normal task loop
            ready = [t for t in ready if not t.id.startswith("REPAIR-")]
            if not ready:
                break

            task = ready[0]
            label = f"Task {task.id}"
            state = self._state()

            # State transition to BUILDING
            if state.status != WorkflowStatus.BUILDING:
                state.status = transition(state.status, WorkflowStatus.BUILDING)
                self._stores.save_state(state)

            self._progress(f"{label}: {task.description}...")
            try:
                b_res = await execute_task(
                    task,
                    builder=builder,
                    stores=self._stores,
                    config=self._config,
                    plan=state.architecture_plan,
                    research=state.research,
                )
            except (KeyboardInterrupt, asyncio.CancelledError):
                raise
            except Exception as exc:  # noqa: BLE001
                self._progress(f"{label} FAILED — {exc}")
                continue

            # Review pass (Expert Coder)
            state = self._state()
            state.status = transition(state.status, WorkflowStatus.REVIEWING)
            self._stores.save_state(state)

            self._progress(f"{label}: reviewing changes...")
            await review_work(
                stores=self._stores,
                config=self._config,
                task_id=task.id,
                coder=coder,
                approval=self._approval,
            )

    async def _verify_and_supervise(self) -> SupervisorReport:
        state = self._state()
        if state.status != WorkflowStatus.TESTING:
            state.status = transition(state.status, WorkflowStatus.TESTING)
            self._stores.save_state(state)

        self._progress("Testing and quality verification...")

        state = self._state()
        state.status = transition(state.status, WorkflowStatus.SUPERVISING)
        self._stores.save_state(state)

        self._progress("Supervisor: auditing repository...")
        supervisor = self._fakes.get("supervisor") or build_supervisor(
            config=self._config,
            workspace=self._stores.root,
            stores=self._stores,
            router=self._router,
            approval=self._approval,
            run_id=self._run.run_id if self._run else None,
        )

        report = await supervise(
            stores=self._stores,
            config=self._config,
            approval=self._approval,
            supervisor=supervisor,
        )
        return report

    async def _repair(self, report: SupervisorReport, incomplete: list[str]) -> None:
        state = self._state()
        state.status = transition(state.status, WorkflowStatus.REPAIRING)
        state.iteration += 1
        self._stores.save_state(state)

        self._stores.recorder.record(
            EventType.REPAIR_STARTED,
            {"iteration": state.iteration, "required_changes": report.required_changes},
            run_id=self._run.run_id if self._run else None,
        )

        repair_id = f"REPAIR-{state.iteration:03d}"
        criteria = list(report.required_changes)
        if incomplete:
            criteria.append(f"Incomplete tasks to finish: {', '.join(incomplete)}")

        repair_task = Task(
            id=repair_id,
            description=f"Self-healing repair iteration {state.iteration}",
            priority=TaskPriority.CRITICAL,
            acceptance_criteria=criteria,
            status=TaskStatus.PENDING,
        )

        self._progress(f"Self-healing repair iteration {state.iteration}...")
        coder = self._fakes.get("coder") or build_coder(
            config=self._config,
            workspace=self._stores.root,
            stores=self._stores,
            router=self._router,
            approval=self._approval,
            run_id=self._run.run_id if self._run else None,
        )

        extra_ctx = (
            f"<supervisor_report>\nStatus: {report.status}\nSummary: {report.summary}\n"
            f"Required changes:\n" + "\n".join(f"- {c}" for c in criteria) + "\n</supervisor_report>"
        )

        await coder.review(
            task=repair_task,
            plan=state.architecture_plan,
            research=state.research,
            diff=git_diff(self._stores.root),
            changed_files=git_changed_files(self._stores.root),
            errors=state.errors[-5:],
            extra_context=extra_ctx,
        )

    def _finish_success(self, report: SupervisorReport) -> BuildRunResult:
        state = self._state()
        state.status = transition(state.status, WorkflowStatus.COMPLETED)
        self._stores.save_state(state)

        cp = create_checkpoint(
            f"completed-run-{self._run.run_id[:8]}" if self._run else "completed",
            stores=self._stores,
            description="Build completed successfully",
            run_id=self._run.run_id if self._run else None,
        )

        if self._run:
            self._run.status = RunStatus.COMPLETED
            self._run.phase = WorkflowStatus.COMPLETED
            self._run.finished_at = datetime.now(UTC)
            self._run.summary = "Build completed successfully with supervisor approval"
            self._stores.runs.update(self._run)

        self._stores.recorder.record(
            EventType.RUN_COMPLETED,
            {"status": "completed", "verdict": report.status},
            run_id=self._run.run_id if self._run else None,
        )

        tasks = [t for t in self._stores.tasks.load() if not t.id.startswith("REPAIR-")]
        completed = [t for t in tasks if t.status == TaskStatus.COMPLETED]

        usage_totals = None
        if self._stores.usage is not None:
            try:
                usage_totals = self._stores.usage.totals()
            except Exception:
                pass

        return BuildRunResult(
            status="completed",
            verdict=report.status,
            reason="Build complete and verified by supervisor",
            tasks_total=len(tasks),
            tasks_completed=len(completed),
            changed_files=state.changed_files,
            tests=report.tests,
            build_ok=report.build.ok if report.build else True,
            iterations=state.iteration,
            checkpoint=cp.git_commit if cp else None,
            warnings=report.warnings,
            usage=usage_totals,
        )

    def _finish_failure(self, reason: str, report: SupervisorReport | None = None) -> BuildRunResult:
        state = self._state()
        state.status = transition(state.status, WorkflowStatus.FAILED)
        self._stores.save_state(state)

        if self._run:
            self._run.status = RunStatus.FAILED
            self._run.phase = WorkflowStatus.FAILED
            self._run.finished_at = datetime.now(UTC)
            self._run.error = reason
            self._stores.runs.update(self._run)

        self._stores.recorder.record(
            EventType.RUN_FAILED,
            {"status": "failed", "reason": reason},
            run_id=self._run.run_id if self._run else None,
        )

        tasks = [t for t in self._stores.tasks.load() if not t.id.startswith("REPAIR-")]
        completed = [t for t in tasks if t.status == TaskStatus.COMPLETED]
        remaining = [t.id for t in tasks if t.status != TaskStatus.COMPLETED]

        usage_totals = None
        if self._stores.usage is not None:
            try:
                usage_totals = self._stores.usage.totals()
            except Exception:
                pass

        return BuildRunResult(
            status="failed",
            verdict=report.status if report else "fail",
            reason=reason,
            tasks_total=len(tasks),
            tasks_completed=len(completed),
            remaining_tasks=remaining,
            changed_files=state.changed_files,
            tests=report.tests if report else None,
            build_ok=report.build.ok if report and report.build else False,
            iterations=state.iteration,
            checkpoint=None,
            warnings=report.warnings if report else [],
            usage=usage_totals,
        )

    def _handle_interrupt(self) -> None:
        state = self._state()
        state.status = WorkflowStatus.CANCELLED
        self._stores.save_state(state)

        if self._run:
            self._run.status = RunStatus.CANCELLED
            self._run.phase = WorkflowStatus.CANCELLED
            self._run.finished_at = datetime.now(UTC)
            self._run.error = "Interrupted by user"
            self._stores.runs.update(self._run)

        self._stores.recorder.record(
            EventType.INTERRUPTED,
            {"stage": "engine_interrupted"},
            run_id=self._run.run_id if self._run else None,
        )

    async def run(
        self,
        request: str | None = None,
        *,
        dry_run: bool = False,
        resume: bool = False,
    ) -> BuildRunResult | DryRunReport:
        state = self._state()
        await self._ensure_agents()

        if dry_run:
            # Plan without persisting
            planner = self._fakes.get("planner") or build_planner(
                config=self._config,
                workspace=self._stores.root,
                stores=self._stores,
                router=self._router,
            )
            req = request or state.user_request or "Default project build"
            res = await planner.plan(req)
            return DryRunReport(
                planned_tasks=[t.model_dump() for t in res.plan.tasks],
                planned_files=list({f for t in res.plan.tasks for f in t.files}),
                libraries=res.plan.libraries,
                detected_tests=detect_test_command(self._stores.root),
                detected_build=detect_build_command(self._stores.root),
                agent_sequence=["architect", "builder", "expert_coder", "supervisor"],
                max_iterations=self._config.workflow.max_iterations,
            )

        lock = RunLock(self._stores.forgex_dir / "run.lock")
        lock.acquire()

        # Handle resume
        if resume:
            self._resuming = True
            tasks = self._stores.tasks.load()
            for t in tasks:
                if t.status == TaskStatus.IN_PROGRESS:
                    t.status = TaskStatus.PENDING
            self._stores.save_tasks(tasks, project_id=state.project_id)
            if state.status in (WorkflowStatus.COMPLETED, WorkflowStatus.FAILED, WorkflowStatus.CANCELLED):
                state.status = WorkflowStatus.BUILDING
            self._stores.save_state(state)

        run = RunState(
            run_id=uuid.uuid4().hex,
            project_id=state.project_id,
            request=request or state.user_request or "build",
            phase=state.status,
        )
        self._stores.runs.create(run)
        self._run = run
        state.current_run_id = run.run_id
        self._stores.save_state(state)

        self._stores.recorder.record(
            EventType.RUN_STARTED,
            {"request": run.request, "run_id": run.run_id},
            run_id=run.run_id,
        )

        try:
            await self._ensure_plan(request)
            await self._task_loop()

            while True:
                report = await self._verify_and_supervise()
                incomplete = self._incomplete_tasks()

                # Gate 0: Implementation complete check
                if report.status == "pass" and not incomplete:
                    return self._finish_success(report)

                if report.status == "needs_review":
                    return self._finish_failure(
                        "supervisor verdict: needs_review (cannot verify)", report
                    )

                state = self._state()
                if state.iteration >= self._max_iterations:
                    return self._finish_failure(
                        f"maximum repair iterations reached ({self._max_iterations})",
                        report,
                    )

                await self._repair(report, incomplete)

        except (KeyboardInterrupt, asyncio.CancelledError):
            self._handle_interrupt()
            raise
        finally:
            await self._cleanup()
            lock.release()

    async def fix(self) -> BuildRunResult:
        """§12/§22 `forgex fix`: on-demand repair loop without replanning."""
        state = self._state()
        await self._ensure_agents()
        self._resuming = True
        if state.status in (
            WorkflowStatus.COMPLETED,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
            WorkflowStatus.INITIALIZING,
        ):
            logger.debug("fix() from state %s — resetting to testing", state.status.value)
            state.status = WorkflowStatus.TESTING
        elif state.status != WorkflowStatus.TESTING:
            state.status = WorkflowStatus.TESTING
        state.iteration = 0
        self._stores.save_state(state)

        lock = RunLock(self._stores.forgex_dir / "run.lock")
        lock.acquire()

        run = RunState(
            run_id=uuid.uuid4().hex,
            project_id=state.project_id,
            request="fix",
            phase=state.status,
        )
        self._stores.runs.create(run)
        self._run = run
        state.current_run_id = run.run_id
        self._stores.save_state(state)

        self._stores.recorder.record(
            EventType.RUN_STARTED,
            {"mode": "fix", "run_id": run.run_id},
            run_id=run.run_id,
        )

        try:
            while True:
                report = await self._verify_and_supervise()
                incomplete = self._incomplete_tasks()
                if report.status == "pass":
                    return self._finish_success(report)
                if report.status == "needs_review":
                    return self._finish_failure(
                        "supervisor verdict: needs_review (cannot verify)", report
                    )
                state = self._state()
                if state.iteration >= self._max_iterations:
                    return self._finish_failure(
                        f"maximum repair iterations reached ({self._max_iterations})",
                        report,
                    )
                await self._repair(report, incomplete)
        except (KeyboardInterrupt, asyncio.CancelledError):
            self._handle_interrupt()
            raise
        finally:
            await self._cleanup()
            lock.release()

    build = run
