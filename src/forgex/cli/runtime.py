"""Autonomous runtime engine for FORGEX Universal CLI.

Unifies project initialization, planning, building, verification,
supervision, self-healing repairs, and git checkpoints into a single,
frictionless autonomous pipeline.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from rich.console import Console

from forgex.cli.build_views import format_progress
from forgex.cli.session import Session
from forgex.cli.ui import UI, Output, make_approval
from forgex.config import load_config
from forgex.orchestration.checkpoints import latest_checkpoint
from forgex.orchestration.engine import BuildEngine, DryRunReport
from forgex.orchestration.stores import open_stores
from forgex.project import initialize_project
from forgex.schemas.result import TestResults
from forgex.utils.paths import find_project_root

logger = logging.getLogger("forgex.runtime")

ProgressFn = Callable[[str], None]


@dataclass
class RuntimeResult:
    """Consolidated outcome of an autonomous execution."""

    status: Literal["completed", "failed"]
    request: str
    phases_completed: list[str] = field(default_factory=list)
    tasks_total: int = 0
    tasks_completed: int = 0
    changed_files: list[str] = field(default_factory=list)
    tests: TestResults | None = None
    build_ok: bool | None = None
    checkpoint_id: str | None = None
    reason: str = ""
    warnings: list[str] = field(default_factory=list)
    usage: dict[str, Any] | None = None
    duration_seconds: float = 0.0

    @property
    def is_success(self) -> bool:
        return self.status == "completed"


class AutonomousRuntime:
    """Unified autonomous pipeline executor for FORGEX.

    Takes a high-level user request in natural language and drives:
    1. Zero-friction project initialization if not already initialized
    2. Architecture planning and task decomposition
    3. Per-task implementation with builder & expert coder
    4. Deterministic testing, linting, and build verification
    5. Supervisor auditing and soft gates
    6. Self-healing repair loops until green (bounded)
    7. Automated git checkpoint snapshot on completion
    """

    def __init__(
        self,
        target_dir: Path | None = None,
        session: Session | None = None,
        ui: UI | None = None,
        progress: ProgressFn | None = None,
        approval: Callable[[str], bool] | None = None,
    ) -> None:
        self.target_dir = Path(target_dir).resolve() if target_dir else Path.cwd()
        self.session = session
        self.ui = ui or (session.ui if session else UI(mode=Output.RICH))
        self.console = self.ui.console if hasattr(self.ui, "console") else Console()
        self._custom_progress = progress
        self._approval = approval or (make_approval(self.ui) if self.ui else None)

    def _notify_progress(self, msg: str) -> None:
        if self._custom_progress:
            self._custom_progress(msg)
        elif self.ui:
            is_rich = getattr(self.ui, "mode", None) is Output.RICH
            self.ui.text(format_progress(msg, rich_mode=is_rich))

    def _ensure_project_initialized(self) -> tuple[Path, bool]:
        """Check if target directory is a FORGEX project; auto-initialize if not."""
        root = find_project_root(self.target_dir)
        was_initialized = False

        if root is None or not (root / ".forgex").is_dir():
            self._notify_progress(f"Initializing project workspace at {self.target_dir}...")
            # Auto-init git if git is available and repo doesn't exist
            git_dir = self.target_dir / ".git"
            if not git_dir.exists():
                try:
                    subprocess.run(
                        ["git", "init"],
                        cwd=self.target_dir,
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                except Exception as exc:
                    logger.debug("git init failed: %s", exc)

            root = initialize_project(self.target_dir)
            was_initialized = True
            if self.session:
                self.session.refresh()
            self._notify_progress("Project workspace initialized.")

        return root, was_initialized

    async def execute(
        self,
        request: str,
        *,
        resume: bool = False,
        dry_run: bool = False,
        agents: dict[str, Any] | None = None,
    ) -> RuntimeResult:
        """Run the full autonomous pipeline for the given task request."""
        start_time = time.time()
        phases: list[str] = []

        root, was_newly_inited = self._ensure_project_initialized()
        if was_newly_inited:
            phases.append("init")

        config = load_config(root)

        with open_stores(root) as stores:
            engine = BuildEngine(
                stores=stores,
                config=config,
                approval=self._approval,
                progress=self._notify_progress,
                agents=agents,
            )

            build_result = await engine.run(
                request=request,
                dry_run=dry_run,
                resume=resume,
            )

        duration = time.time() - start_time

        if isinstance(build_result, DryRunReport):
            phases.extend(["plan", "preview"])
            return RuntimeResult(
                status="completed",
                request=request,
                phases_completed=phases,
                tasks_total=len(build_result.planned_tasks),
                tasks_completed=0,
                changed_files=build_result.planned_files,
                reason="Dry run preview generated successfully",
                duration_seconds=duration,
            )

        phases.extend(["plan", "build", "verify", "supervise"])

        checkpoint_id = build_result.checkpoint
        if build_result.status == "completed":
            phases.append("checkpoint")
            # If checkpoint wasn't automatically populated by git, look up latest checkpoint
            if not checkpoint_id and (root / ".git").exists():
                try:
                    with open_stores(root) as stores:
                        latest = latest_checkpoint(stores=stores)
                        if latest:
                            checkpoint_id = latest.git_commit
                except Exception:
                    pass

        runtime_res = RuntimeResult(
            status=build_result.status,
            request=request,
            phases_completed=phases,
            tasks_total=build_result.tasks_total,
            tasks_completed=build_result.tasks_completed,
            changed_files=build_result.changed_files,
            tests=build_result.tests,
            build_ok=build_result.build_ok,
            checkpoint_id=checkpoint_id,
            reason=build_result.reason,
            warnings=build_result.warnings,
            usage=build_result.usage,
            duration_seconds=duration,
        )

        if self.session:
            self.session.refresh()

        return runtime_res


def execute_autonomous(
    request: str,
    target_dir: Path | None = None,
    session: Session | None = None,
    ui: UI | None = None,
    dry_run: bool = False,
    resume: bool = False,
    approval: Callable[[str], bool] | None = None,
    agents: dict[str, Any] | None = None,
) -> RuntimeResult:
    """Synchronous convenience wrapper for AutonomousRuntime.execute()."""
    runtime = AutonomousRuntime(
        target_dir=target_dir,
        session=session,
        ui=ui,
        approval=approval,
    )
    return asyncio.run(
        runtime.execute(
            request=request,
            dry_run=dry_run,
            resume=resume,
            agents=agents,
        )
    )
