import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from forgex.cli.app import app

runner = CliRunner()


def git_project(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir(exist_ok=True)
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["init"])
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True, capture_output=True)
    return tmp_path


def test_checkpoint_and_rollback_cli(tmp_path: Path, monkeypatch):
    git_project(tmp_path, monkeypatch)
    (tmp_path / "a.txt").write_text("v1", encoding="utf-8")

    cp1 = runner.invoke(app, ["checkpoint", "first", "--json"])
    assert cp1.exit_code == 0, cp1.output
    cp1_id = json.loads(cp1.output)["id"]

    (tmp_path / "a.txt").write_text("v2", encoding="utf-8")
    runner.invoke(app, ["checkpoint", "second"])

    result = runner.invoke(app, ["rollback", cp1_id, "--yes", "--json"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "v1"
    payload = json.loads(result.output)
    assert payload["safety_checkpoint"]  # rollback is reversible


def test_rollback_requires_yes_when_non_interactive(tmp_path: Path, monkeypatch):
    git_project(tmp_path, monkeypatch)
    (tmp_path / "a.txt").write_text("v1", encoding="utf-8")
    runner.invoke(app, ["checkpoint", "first"])
    (tmp_path / "a.txt").write_text("v2", encoding="utf-8")
    result = runner.invoke(app, ["rollback"])  # no --yes
    assert result.exit_code == 1
    assert "Refusing" in result.output or "--yes" in result.output


def test_diff_command(tmp_path: Path, monkeypatch):
    git_project(tmp_path, monkeypatch)
    (tmp_path / "a.txt").write_text("v1", encoding="utf-8")
    runner.invoke(app, ["checkpoint", "first"])
    (tmp_path / "a.txt").write_text("v2", encoding="utf-8")
    result = runner.invoke(app, ["diff"])
    assert result.exit_code == 0
    assert "+v2" in result.output


def test_checkpoint_without_git_warns(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["init"])
    result = runner.invoke(app, ["checkpoint", "x"])
    assert result.exit_code == 0
    assert "git" in result.output.lower()
