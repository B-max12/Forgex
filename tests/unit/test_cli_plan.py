import json
from pathlib import Path

from typer.testing import CliRunner

from forgex.cli.app import app
from forgex.orchestration.events import read_events
from forgex.orchestration.state import StateStore, TaskStore
from forgex.schemas.event import EventType
from forgex.schemas.plan import ArchitectResult, ArchitecturePlan
from forgex.schemas.research import ResearchNote

runner = CliRunner()


def plan_payload() -> dict:
    return {
        "goal": "FastAPI Todo API with SQLite",
        "requirements": ["CRUD", "tests"],
        "tasks": [
            {"id": "TASK-001", "description": "Scaffold app", "priority": "high"},
            {"id": "TASK-002", "description": "Wire SQLite", "depends_on": ["TASK-001"]},
            {"id": "TASK-003", "description": "Add tests", "depends_on": ["TASK-001"]},
        ],
        "libraries": ["fastapi", "pytest"],
    }


class FakePlanner:
    def __init__(self):
        self.requests = []

    async def plan(self, request, *, on_stage=None):
        self.requests.append(request)
        if on_stage:
            for stage in ("analyzing", "researching", "planning"):
                on_stage(stage)
        return ArchitectResult(
            plan=ArchitecturePlan.model_validate(plan_payload()),
            research=[ResearchNote(topic="pypi:fastapi", source="pypi",
                                   summary="FastAPI framework", version="0.115.0",
                                   confidence="high")],
        )


def install_fake(monkeypatch):
    fake = FakePlanner()
    monkeypatch.setattr("forgex.cli.commands.plan.build_planner", lambda **kwargs: fake)
    return fake


def test_plan_persists(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    install_fake(monkeypatch)
    runner.invoke(app, ["init"])

    result = runner.invoke(app, ["plan", "Build a todo API", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["tasks_created"] == 3
    assert payload["persisted"] is True

    state = StateStore(tmp_path).load()
    assert state.status.value == "planning"
    assert state.user_request == "Build a todo API"
    assert state.tasks == ["TASK-001", "TASK-002", "TASK-003"]
    assert state.architecture_plan is not None
    tasks = TaskStore(tmp_path).load()
    assert [t.id for t in tasks] == ["TASK-001", "TASK-002", "TASK-003"]
    types = [e.type for e in read_events(tmp_path / ".forgex" / "events.jsonl")]
    assert EventType.PLAN_CREATED in types


def test_plan_dry_run_persists_nothing(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    install_fake(monkeypatch)
    runner.invoke(app, ["init"])

    result = runner.invoke(app, ["plan", "Build a todo API", "--dry-run", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["persisted"] is False

    state = StateStore(tmp_path).load()
    assert state.status.value == "initializing"  # untouched
    assert TaskStore(tmp_path).load() == []


def test_replanning_is_allowed(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    install_fake(monkeypatch)
    runner.invoke(app, ["init"])
    first = runner.invoke(app, ["plan", "first request"])
    second = runner.invoke(app, ["plan", "second request"])
    assert first.exit_code == 0 and second.exit_code == 0
    assert StateStore(tmp_path).load().user_request == "second request"


def test_plan_outside_project_fails(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["plan", "anything"])
    assert result.exit_code == 4  # ProjectError
