from __future__ import annotations

from pathlib import Path
import pytest

from forgex.schemas.error import CommandDeniedError
from forgex.sandbox.executor import RestrictedLocalExecutor
from forgex.sandbox.policies import CommandPolicy
from forgex.tools.verification import (
    detect_build_command,
    detect_lint_command,
    detect_test_command,
    run_verification,
)


def make_executor(root: Path):
    return RestrictedLocalExecutor(workspace=root, policy=CommandPolicy())


def test_detect_lint_command_none(tmp_path):
    bare = tmp_path / "bare"
    bare.mkdir()
    (bare / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    assert detect_lint_command(bare) is None


async def test_run_verification_passing_project(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\ndependencies = ["pytest"]\n', encoding="utf-8")
    (tmp_path / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")

    outcome = await run_verification(root=tmp_path, executor=make_executor(tmp_path))
    assert outcome.tests is not None and outcome.tests.ok
    assert outcome.tests.passed == 1 and outcome.tests.failed == 0
    assert outcome.build is not None and outcome.build.ok
    assert outcome.lint is None  # not configured → skipped


async def test_run_verification_failing_tests(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\ndependencies = ["pytest"]\n', encoding="utf-8")
    (tmp_path / "test_bad.py").write_text(
        "def test_bad():\n    assert False\n", encoding="utf-8")
    outcome = await run_verification(root=tmp_path, executor=make_executor(tmp_path))
    assert outcome.tests is not None and not outcome.tests.ok
    assert outcome.tests.failed == 1


async def test_run_verification_build_catches_syntax_error(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "broken.py").write_text("def f(:\n", encoding="utf-8")
    outcome = await run_verification(root=tmp_path, executor=make_executor(tmp_path))
    assert outcome.build is not None and not outcome.build.ok
    assert outcome.tests is None  # no test framework detected


async def test_run_verification_lint_gate(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[tool.ruff]\n", encoding="utf-8")
    (tmp_path / "smelly.py").write_text("import os\nx = 1\n", encoding="utf-8")
    outcome = await run_verification(root=tmp_path, executor=make_executor(tmp_path))
    assert outcome.lint is not None and not outcome.lint.ok


async def test_run_verification_denied_command_is_soft(tmp_path):
    class DenyingExecutor:
        async def run(self, argv, **kwargs):
            raise CommandDeniedError("command denied by policy: test deny")

    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\ndependencies = ["pytest"]\n', encoding="utf-8")
    outcome = await run_verification(root=tmp_path, executor=DenyingExecutor())
    assert outcome.tests is not None
    assert outcome.tests.exit_code is None
    assert "not run" in outcome.tests.output_tail
