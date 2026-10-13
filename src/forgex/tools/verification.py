"""Deterministic verification harness (spec sections 11, 56)."""

from __future__ import annotations

import json
import re
from pathlib import Path

from forgex.orchestration.events import EventRecorder
from forgex.project import detect_project
from forgex.sandbox.executor import CommandExecutor
from forgex.schemas.error import CommandDeniedError
from forgex.schemas.event import EventType
from forgex.schemas.result import (
    BuildResults,
    CommandOutcome,
    TestResults,
    VerificationOutcome,
)
from forgex.tools.testing import detect_test_command


def detect_build_command(root: Path) -> list[str] | None:
    det = detect_project(root)
    langs = det.languages

    if (root / "package.json").is_file():
        try:
            data = json.loads((root / "package.json").read_text(encoding="utf-8"))
            if (data.get("scripts") or {}).get("build"):
                return ["npm", "run", "build"]
        except (OSError, json.JSONDecodeError):
            pass

    if "Rust" in langs or (root / "Cargo.toml").is_file():
        return ["cargo", "build"]

    if "Go" in langs or (root / "go.mod").is_file():
        return ["go", "build", "./..."]

    if "Python" in langs:
        src_dir = root / "src"
        if src_dir.is_dir():
            return ["python", "-m", "compileall", "-q", "src"]
        if list(root.glob("*.py")):
            return ["python", "-m", "compileall", "-q", "."]

    return None


def detect_lint_command(root: Path) -> list[str] | None:
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            content = pyproject.read_text(encoding="utf-8", errors="replace")
            if "[tool.ruff]" in content:
                return ["python", "-m", "ruff", "check", "."]
        except OSError:
            pass

    pkg = root / "package.json"
    if pkg.is_file():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
            if (data.get("scripts") or {}).get("lint"):
                return ["npm", "run", "lint"]
        except (OSError, json.JSONDecodeError):
            pass

    return None


def parse_pytest_summary(output: str) -> tuple[int | None, int | None, int | None]:
    """Parse passed, failed, errors counts from pytest output summary."""
    passed = None
    failed = None
    errors = None

    p_match = re.search(r"(\d+)\s+passed", output)
    if p_match:
        passed = int(p_match.group(1))

    f_match = re.search(r"(\d+)\s+failed", output)
    if f_match:
        failed = int(f_match.group(1))

    e_match = re.search(r"(\d+)\s+error", output)
    if e_match:
        errors = int(e_match.group(1))

    if passed is not None and failed is None:
        failed = 0
    if failed is not None and passed is None:
        passed = 0

    return passed, failed, errors


async def _step(command: list[str], executor: CommandExecutor) -> CommandOutcome:
    try:
        res = await executor.run(command, cwd=".")
        tail = (res.stdout + "\n" + res.stderr)[-4000:].strip()
        return CommandOutcome(
            command=command,
            exit_code=res.exit_code,
            timed_out=res.timed_out,
            duration_ms=round(res.duration_ms, 1),
            output_tail=tail,
        )
    except CommandDeniedError as exc:
        return CommandOutcome(
            command=command,
            exit_code=None,
            timed_out=False,
            output_tail=f"not run (command denied by policy: {exc})",
        )


async def run_verification(
    root: Path,
    executor: CommandExecutor,
    events: EventRecorder | None = None,
    run_id: str | None = None,
    include_build: bool = True,
    include_lint: bool = True,
) -> VerificationOutcome:
    outcome = VerificationOutcome()

    test_cmd = detect_test_command(root)
    if test_cmd:
        if events is not None:
            events.record(EventType.TEST_STARTED, {"command": test_cmd}, run_id=run_id)
        base = await _step(test_cmd, executor)
        passed, failed, errors = parse_pytest_summary(base.output_tail)
        outcome.tests = TestResults(
            command=base.command,
            exit_code=base.exit_code,
            timed_out=base.timed_out,
            duration_ms=base.duration_ms,
            output_tail=base.output_tail,
            passed=passed,
            failed=failed,
            errors=errors,
        )
        if events is not None:
            events.record(
                EventType.TEST_COMPLETED,
                {
                    "exit_code": base.exit_code,
                    "passed": passed,
                    "failed": failed,
                    "timed_out": base.timed_out,
                },
                run_id=run_id,
            )

    if include_build:
        build_cmd = detect_build_command(root)
        if build_cmd:
            base_build = await _step(build_cmd, executor)
            outcome.build = BuildResults(
                command=base_build.command,
                exit_code=base_build.exit_code,
                timed_out=base_build.timed_out,
                duration_ms=base_build.duration_ms,
                output_tail=base_build.output_tail,
            )

    if include_lint:
        lint_cmd = detect_lint_command(root)
        if lint_cmd:
            outcome.lint = await _step(lint_cmd, executor)

    return outcome
