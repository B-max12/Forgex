import json
import sys
from pathlib import Path

from typer.testing import CliRunner

from forgex.cli.app import app
from forgex.cli.commands.run import detect_run_command
from forgex.orchestration.stores import open_stores
from forgex.schemas.result import ModelUsageRecord

runner = CliRunner()


def test_detect_run_command(tmp_path):
    (tmp_path / "package.json").write_text(
        '{"scripts": {"start": "node server.js"}}', encoding="utf-8")
    assert detect_run_command(tmp_path) == ["npm", "start"]
    bare = tmp_path / "bare"
    bare.mkdir()
    assert detect_run_command(bare) is None


def test_cli_run_explicit_command(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["init"])
    result = runner.invoke(
        app, ["run", "--", sys.executable, "-c", "print('app running')"])
    assert result.exit_code == 0, result.output
    assert "app running" in result.output


def test_cli_run_without_command_is_guided(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["init"])
    result = runner.invoke(app, ["run"])
    assert result.exit_code == 4  # ProjectError with usage hint


def test_status_shows_model_usage(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["init"])
    with open_stores(tmp_path) as stores:
        stores.usage.insert(ModelUsageRecord(
            agent="architect", provider="groq", model="llama-3.3-70b-versatile",
            input_tokens=100, output_tokens=50, total_tokens=150))
    result = runner.invoke(app, ["status", "--json"])
    assert result.exit_code == 0, result.output
    usage = json.loads(result.output)["model_usage"]
    assert usage["calls"] == 1 and usage["input_tokens"] == 100
