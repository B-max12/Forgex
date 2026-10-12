from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from forgex import __version__
from forgex.cli.app import app

runner = CliRunner()


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "FORGEX" in result.output


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_doctor_json(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["ok"] is True
    names = [c["name"] for c in payload["checks"]]
    assert "Python" in names and "SQLite" in names


def test_init_then_status(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r1 = runner.invoke(app, ["init"])
    assert r1.exit_code == 0
    r2 = runner.invoke(app, ["status", "--json"])
    assert r2.exit_code == 0
    payload = json.loads(r2.output)
    assert payload["project"] == tmp_path.name
    assert payload["events"] >= 1


def test_status_outside_project_fails(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 4  # ProjectError


def test_config_set_get(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["init"])
    r = runner.invoke(app, ["config", "set", "workflow.max_iterations", "9"])
    assert r.exit_code == 0
    r = runner.invoke(app, ["config", "get", "workflow.max_iterations", "--json"])


def test_logs_after_init(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["init"])
    result = runner.invoke(app, ["logs"])
    assert result.exit_code == 0
    assert "ProjectInitialized" in result.output


def test_logs_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["init"])
    result = runner.invoke(app, ["logs", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output.strip().splitlines()[-1])
    assert payload["type"] == "ProjectInitialized"


def test_logs_unknown_type_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["init"])
    result = runner.invoke(app, ["logs", "--type", "Bogus"])
    assert result.exit_code == 2  # ConfigError


def test_status_shows_state_and_tasks(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["init"])
    result = runner.invoke(app, ["status", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["state"]["status"] == "initializing"
    assert payload["tasks"]["total"] == 0
    assert payload["state"]["project_id"]
