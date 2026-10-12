from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from forgex.config import load_config
from forgex.orchestration.engine import BuildEngine
from forgex.orchestration.state import StateStore, TaskStore
from forgex.orchestration.stores import open_stores
from forgex.project import initialize_project
from forgex.schemas.agent import (
    ArchitectResult,
    BuilderResult,
    ExpertCoderResult,
    SupervisorJudgment,
)
from forgex.schemas.plan import ArchitecturePlan
from forgex.schemas.task import Task, TaskStatus

PLAN = [
    {"id": "TASK-001", "description": "First"},
    {"id": "TASK-002", "description": "Second", "depends_on": ["TASK-001"]},
]
PASSING_TEST = "def test_x():\n    assert True\n"
FAILING_TEST = "def test_x():\n    assert False\n"


class FakePlanner:
    def __init__(self, plan_tasks=None):
        self.plan_tasks = plan_tasks or PLAN

    async def plan(self, request, *, on_stage=None):
        return ArchitectResult(
            plan=ArchitecturePlan.model_validate(
                {"goal": "x", "tasks": self.plan_tasks}
            )
        )

    async def aclose(self):
        return None


class FakeBuilder:
    def __init__(self, fail=(), interrupt_on=None):
        self.fail = set(fail)
        self.interrupt_on = interrupt_on
        self.ran: list[str] = []

    async def execute(self, task, *, plan, research=None):
        self.ran.append(task.id)
        if self.interrupt_on == task.id:
            raise KeyboardInterrupt
        if task.id in self.fail:
            return BuilderResult(
                status="failed", summary=f"cannot build {task.id}", issues=["stubborn failure"]
            )
        return BuilderResult(
            status="completed", summary=f"built {task.id}", changed_files=[f"out_{task.id}.txt"]
        )

    async def aclose(self):
        return None


class FakeCoder:
    def __init__(self, fix=None):
        self.fix = fix
        self.calls: list[str | None] = []

    async def review(
        self,
        *,
        task=None,
        plan=None,
        research=None,
        diff="",
        changed_files=None,
        errors=None,
        extra_context="",
    ):
        self.calls.append(task.id if task else None)
        if self.fix is not None and task and task.id.startswith("REPAIR-"):
            self.fix()
            return ExpertCoderResult(
                status="completed",
                summary="repaired",
                changed_files=["test_x.py"],
                improvements=["fixed the failing test"],
            )
        return ExpertCoderResult(status="completed", summary="reviewed; clean")

    async def aclose(self):
        return None


class FakeSupervisor:
    def __init__(self, verdict="pass"):
        self.verdict = verdict
        self.calls = 0

    async def audit(self, **kwargs):
        self.calls += 1
        return SupervisorJudgment(status=self.verdict, summary="checked")

    async def aclose(self):
        return None


def seed(tmp_path: Path, monkeypatch, *, plan_tasks=PLAN, test_body=PASSING_TEST) -> None:
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir(exist_ok=True)
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, check=True)
    initialize_project(tmp_path)
    (tmp_path / "pyproject.toml").write_text('[project]\nname="demo"\ndependencies=["pytest"]\n', encoding="utf-8")
    (tmp_path / "test_x.py").write_text(test_body, encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "init", "-q"], cwd=tmp_path, check=True)
    with open_stores(tmp_path) as stores:
        tasks = [
            Task(id=t["id"], description=t["description"], depends_on=t.get("depends_on", []))
            for t in plan_tasks
        ]
        state = stores.state.load()
        state.architecture_plan = ArchitecturePlan.model_validate({"goal": "demo", "tasks": plan_tasks})
        stores.save_state(state)
        stores.save_tasks(tasks, project_id=state.project_id)


async def run_engine(
    tmp_path: Path,
    *,
    planner=None,
    builder=None,
    coder=None,
    supervisor=None,
    max_iterations=3,
    resume=False,
):
    agents = {
        "planner": planner or FakePlanner(),
        "builder": builder or FakeBuilder(),
        "coder": coder or FakeCoder(),
        "supervisor": supervisor or FakeSupervisor(),
    }
    with open_stores(tmp_path) as stores:
        engine = BuildEngine(
            stores=stores,
            config=load_config(tmp_path),
            agents=agents,
            max_iterations=max_iterations,
        )
        return await engine.build(request="demo", resume=resume)


async def test_engine_happy_path(tmp_path: Path, monkeypatch):
    seed(tmp_path, monkeypatch)
    res = await run_engine(tmp_path)
    assert res.status == "completed"


async def test_engine_lying_supervisor_rejected(tmp_path: Path, monkeypatch):
    seed(tmp_path, monkeypatch)
    res = await run_engine(tmp_path, builder=FakeBuilder(fail={"TASK-001"}), max_iterations=1)
    assert res.status != "completed"
