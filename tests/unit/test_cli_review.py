from __future__ import annotations

import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from forgex.cli.app import app
from forgex.orchestration.stores import StateStore
from forgex.schemas.agent import ExpertCoderResult

runner = CliRunner()


class FakeCoder:
    def __init__(self):
        self.calls = []

    async def review(self, **kwargs):
        self.calls.append(kwargs)
        return ExpertCoderResult(
            status="completed",
            summary="tightened code",
            improvements=["removed unused import"],
            changed_files=["src/a.py"],
        )

    async def aclose(self):
        return None


def install_fake(monkeypatch):
    fake = FakeCoder()
    monkeypatch.setattr("forgex.agents.expert_coder.build_coder", lambda **kwargs: fake)
    return fake


def git_project(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir(exist_ok=True)
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["init"])
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True, capture_output=True)
    return tmp_path


def test_review_cli_reports_improvements(tmp_path: Path, monkeypatch):
    git_project(tmp_path, monkeypatch)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("import os\nx = 1\n", encoding="utf-8")
    install_fake(monkeypatch)

    result = runner.invoke(app, ["review", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["reviewed"] is True
    assert payload["improvements"] == ["removed unused import"]
    assert "src/a.py" in StateStore(tmp_path).load().changed_files


def test_review_cli_nothing_to_review(tmp_path: Path, monkeypatch):
    git_project(tmp_path, monkeypatch)
    result = runner.invoke(app, ["review", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["reviewed"] is False


def test_review_cli_unknown_task(tmp_path: Path, monkeypatch):
    git_project(tmp_path, monkeypatch)
    result = runner.invoke(app, ["review", "--task", "BOGUS-999", "--json"])
    assert result.exit_code != 0
