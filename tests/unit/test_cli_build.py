import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from forgex.cli.app import app
from forgex.orchestration.state import StateStore
from forgex.orchestration.stores import open_stores
from forgex.schemas.plan import ArchitecturePlan, specs_to_tasks

runner = CliRunner()


def test_cli_build_end_to_end(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir(exist_ok=True)
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["init"])
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\ndependencies = ["pytest"]\n', encoding="utf-8")
    (tmp_path / "test_x.py").write_text("def test_x():\n    assert True\n",
                                        encoding="utf-8")
    plan = ArchitecturePlan.model_validate({
        "goal": "demo",
        "tasks": [{"id": "TASK-001", "description": "First"},
                  {"id": "TASK-002", "description": "Second"}]})
    with open_stores(tmp_path) as stores:
        state = stores.state.load()
        state.user_request = "demo build"
        state.architecture_plan = plan
        stores.save_state(state)
        stores.save_tasks(specs_to_tasks(plan.tasks), project_id=state.project_id)

    # fake the four agent factories inside the engine module
    from tests.unit.test_engine import FakeBuilder, FakeCoder, FakePlanner, FakeSupervisor

    monkeypatch.setattr("forgex.orchestration.engine.build_planner",
                        lambda **kw: FakePlanner())
    monkeypatch.setattr("forgex.orchestration.engine.build_builder",
                        lambda **kw: FakeBuilder())
    monkeypatch.setattr("forgex.orchestration.engine.build_coder",
                        lambda **kw: FakeCoder())
    monkeypatch.setattr("forgex.orchestration.engine.build_supervisor",
                        lambda **kw: FakeSupervisor())

    result = runner.invoke(app, ["build", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "completed"
    assert payload["tasks_completed"] == 2
    assert payload["verdict"] == "pass"
    assert StateStore(tmp_path).load().status.value == "completed"


def test_cli_build_requires_request_on_empty_project(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["init"])
    result = runner.invoke(app, ["build"])
    assert result.exit_code == 4  # ProjectError: provide a request
