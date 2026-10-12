import json
from pathlib import Path

from typer.testing import CliRunner

from forgex.cli.app import app
from forgex.schemas.agent import SupervisorJudgment

runner = CliRunner()


def seed(tmp_path: Path, *, failing=False):
    runner.invoke(app, ["init"])
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\ndependencies = ["pytest"]\n', encoding="utf-8")
    (tmp_path / "test_x.py").write_text(
        "def test_x():\n    assert " + ("False" if failing else "True") + "\n",
        encoding="utf-8")


def test_verify_pass(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    seed(tmp_path)
    result = runner.invoke(app, ["verify", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["tests"]["passed"] == 1
    assert payload["lint"] is None


def test_verify_fail(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    seed(tmp_path, failing=True)
    result = runner.invoke(app, ["verify", "--json"])
    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["tests"]["failed"] == 1


class FakeSupervisorCLI:
    async def audit(self, **kwargs):
        return SupervisorJudgment(status="pass", summary="verified")

    async def aclose(self):
        return None


def test_supervise_cli(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    seed(tmp_path)
    monkeypatch.setattr("forgex.agents.supervisor.build_supervisor",
                        lambda **kwargs: FakeSupervisorCLI())
    result = runner.invoke(app, ["supervise", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "pass"
    assert payload["tests"]["passed"] == 1


def test_supervise_cli_exit_nonzero_on_fail(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    seed(tmp_path, failing=True)
    monkeypatch.setattr("forgex.agents.supervisor.build_supervisor",
                        lambda **kwargs: FakeSupervisorCLI())
    result = runner.invoke(app, ["supervise", "--json"])
    assert result.exit_code == 1
