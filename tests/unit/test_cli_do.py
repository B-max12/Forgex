from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from forgex.cli.app import app
from forgex.schemas.agent import ArchitectResult
from forgex.schemas.plan import ArchitecturePlan

runner = CliRunner()


class FakePlanner:
    async def plan(self, request, *, on_stage=None):
        return ArchitectResult(
            plan=ArchitecturePlan.model_validate({
                "goal": request,
                "tasks": [
                    {"id": "TASK-001", "description": "Scaffold service"},
                ],
                "libraries": [],
            })
        )

    async def aclose(self):
        return None


def test_cli_do_dry_run(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "forgex.orchestration.engine.build_planner",
        lambda **kwargs: FakePlanner(),
    )

    res = runner.invoke(app, ["do", "Create payment service", "--dry-run", "--json"])
    assert res.exit_code == 0, res.output
    data = json.loads(res.output)
    assert data["status"] == "completed"
    assert data["request"] == "Create payment service"
    assert data["tasks_total"] == 1
    assert "init" in data["phases"]
    assert "plan" in data["phases"]


def test_cli_dynamic_command_routing_to_do(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "forgex.orchestration.engine.build_planner",
        lambda **kwargs: FakePlanner(),
    )

    # Calling with prose instead of a known command
    res = runner.invoke(app, ["build me a microservice", "--dry-run", "--json"])
    assert res.exit_code == 0, res.output
    data = json.loads(res.output)
    assert data["status"] == "completed"
    assert "build me a microservice" in data["request"]


def test_cli_do_missing_request():
    res = runner.invoke(app, ["do"])
    assert res.exit_code != 0
