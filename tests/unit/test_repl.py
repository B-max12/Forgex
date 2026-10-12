from pathlib import Path
from unittest.mock import MagicMock

import pytest

from forgex.cli.repl import ForgexREPL
from forgex.cli.session import Session
from forgex.project import initialize_project


def test_repl_init_and_prompt(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    session = Session()
    repl = ForgexREPL(session=session)
    prompt_html = repl.get_prompt_text()
    assert "forgex" in prompt_html.value

    initialize_project(tmp_path)
    session.refresh()
    prompt_html_attached = repl.get_prompt_text()
    assert tmp_path.name in prompt_html_attached.value


def test_repl_help_and_banner_run_without_error(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    repl = ForgexREPL()
    repl.print_banner()
    repl.print_help()
    repl.check_first_run()


def test_repl_dispatch_exit(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    repl = ForgexREPL()
    with pytest.raises(EOFError):
        repl.dispatch("exit")
    with pytest.raises(EOFError):
        repl.dispatch("/quit")


def test_repl_dispatch_cd(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    sub = tmp_path / "subdir"
    sub.mkdir()
    repl = ForgexREPL()
    repl.dispatch(f"cd {sub}")
    assert Path.cwd() == sub.resolve()


def test_repl_dispatch_command_execution(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    repl = ForgexREPL()
    repl._run_cli_command = MagicMock()
    repl.dispatch("doctor --json")
    repl._run_cli_command.assert_called_once_with(["doctor", "--json"])


def test_repl_dispatch_natural_language(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    repl = ForgexREPL()
    repl._run_cli_command = MagicMock(return_value=True)
    repl.dispatch("show status")
    repl._run_cli_command.assert_called_once_with(["status"])


def test_repl_dispatch_pipeline(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    repl = ForgexREPL()
    repl._run_cli_command = MagicMock(return_value=True)
    repl.dispatch("build me a REST API")
    assert repl._run_cli_command.call_count == 2
    assert repl._run_cli_command.call_args_list[0][0][0] == ["plan", "a REST API"]
    assert repl._run_cli_command.call_args_list[1][0][0] == ["build"]
