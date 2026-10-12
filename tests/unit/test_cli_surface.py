import pytest
from typer.testing import CliRunner

from forgex.cli.app import app

runner = CliRunner()

ALL_COMMANDS = ["init", "plan", "build", "task", "review", "verify", "supervise",
                "fix", "run", "status", "logs", "diff", "checkpoint", "rollback",
                "models", "context", "tools", "config", "doctor", "repl"]


@pytest.mark.parametrize("command", ALL_COMMANDS)
def test_command_help_renders(command):
    """The full CLI surface imports and renders — one regression test for
    the whole command registry."""
    result = runner.invoke(app, [command, "--help"])
    assert result.exit_code == 0, (command, result.output)
    assert "Usage" in result.output


def test_root_help_lists_pipeline_commands():
    result = runner.invoke(app, ["--help"])
    for command in ("build", "fix", "run", "plan", "review", "supervise", "verify"):
        assert command in result.output
