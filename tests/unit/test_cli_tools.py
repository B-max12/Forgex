import json
import sys
from pathlib import Path

from typer.testing import CliRunner

from forgex.cli.app import app

runner = CliRunner()


def test_tools_list(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["tools", "list", "--json"])
    assert result.exit_code == 0, result.output
    names = {t["name"] for t in json.loads(result.output)["tools"]}
    assert {"read_file", "write_file", "run_command", "run_tests", "git_checkpoint"} <= names


def test_tools_run_write_and_read(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["init"])
    w = runner.invoke(app, ["tools", "run", "write_file", "--agent", "builder",
                            "--args", json.dumps({"path": "hello.txt", "content": "hi"})])
    assert w.exit_code == 0, w.output
    r = runner.invoke(app, ["tools", "run", "read_file", "--agent", "builder",
                            "--args", json.dumps({"path": "hello.txt"})])
    assert r.exit_code == 0
    payload = json.loads(r.output)
    assert "hi" in payload["output"]


def test_tools_run_architect_denied(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["init"])
    result = runner.invoke(app, ["tools", "run", "write_file", "--agent", "architect",
                                 "--args", json.dumps({"path": "x.txt", "content": "y"})])
    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["denied"] is True


def test_tools_run_command_sanitized_env(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["init"])
    monkeypatch.setenv("FORGEX_GROQ_API_KEY", "gsk-leak-check")
    args = json.dumps({"command": [sys.executable, "-c",
                                   "import os; print(os.environ.get('FORGEX_GROQ_API_KEY','CLEAN'))"]})
    result = runner.invoke(app, ["tools", "run", "run_command", "--agent", "builder",
                                 "--args", args, "--json"])
    assert result.exit_code == 0, result.output
    assert "CLEAN" in result.output and "gsk-leak-check" not in result.output
