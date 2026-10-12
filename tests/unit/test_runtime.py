from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from forgex.cli.runtime import AutonomousRuntime, execute_autonomous
from forgex.cli.session import Session
from forgex.schemas.agent import (
    ArchitectResult,
    BuilderResult,
    ExpertCoderResult,
    SupervisorJudgment,
)
from forgex.schemas.plan import ArchitecturePlan


class FakePlanner:
    async def plan(self, request, *, on_stage=None):
        return ArchitectResult(
            plan=ArchitecturePlan.model_validate({
                "goal": request,
                "tasks": [
                    {"id": "TASK-001", "description": "Create schema"},
                    {"id": "TASK-002", "description": "Add routes", "depends_on": ["TASK-001"]},
                ],
                "libraries": ["fastapi"],
            })
        )

    async def aclose(self):
        return None


class FakeBuilder:
    async def execute(self, task, *, plan, research=None):
        return BuilderResult(
            status="completed",
            summary=f"built {task.id}",
            changed_files=[f"{task.id.lower()}.py"],
        )

    async def aclose(self):
        return None


class FakeCoder:
    async def review(self, **kwargs):
        return ExpertCoderResult(
            status="completed",
            summary="reviewed",
            changed_files=[],
            improvements=[],
            passed=True,
        )

    async def aclose(self):
        return None


class FakeSupervisor:
    async def audit(self, **kwargs):
        return SupervisorJudgment(status="pass", issues=[], warnings=[])

    async def aclose(self):
        return None


@pytest.mark.asyncio
async def test_autonomous_runtime_auto_inits(tmp_path: Path):
    runtime = AutonomousRuntime(target_dir=tmp_path)
    # Target directory is initially not a forgex project
    assert not (tmp_path / ".forgex").is_dir()

    # Dry-run execution
    fake_agents = {"planner": FakePlanner()}
    res = await runtime.execute("Design user API", dry_run=True, agents=fake_agents)

    assert (tmp_path / ".forgex").is_dir()
    assert res.is_success
    assert "init" in res.phases_completed
    assert "plan" in res.phases_completed
    assert res.tasks_total == 2


@pytest.mark.asyncio
async def test_autonomous_runtime_full_pipeline(tmp_path: Path, monkeypatch):
    import subprocess
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, check=True)
    (tmp_path / "pyproject.toml").write_text('[project]\nname="demo"\ndependencies=["pytest"]\n', encoding="utf-8")
    (tmp_path / "test_x.py").write_text("def test_x(): assert True\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "init", "-q"], cwd=tmp_path, check=True)

    session = Session()
    runtime = AutonomousRuntime(target_dir=tmp_path, session=session)
    fake_agents = {
        "planner": FakePlanner(),
        "builder": FakeBuilder(),
        "expert_coder": FakeCoder(),
        "supervisor": FakeSupervisor(),
    }

    res = await runtime.execute("Build user auth", agents=fake_agents)

    assert res.is_success
    assert "plan" in res.phases_completed
    assert "build" in res.phases_completed
    assert "verify" in res.phases_completed
    assert res.tasks_completed == 2


def test_execute_autonomous_sync_wrapper(tmp_path: Path):
    fake_agents = {"planner": FakePlanner()}
    res = execute_autonomous("Preview task", target_dir=tmp_path, dry_run=True, agents=fake_agents)
    assert res.is_success
    assert (tmp_path / ".forgex").is_dir()
