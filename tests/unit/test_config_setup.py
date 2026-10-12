from __future__ import annotations

import sys
from pathlib import Path

from forgex.cli.commands.config import SetupAnswers, apply_setup
from forgex.config import load_config


def test_apply_setup_writes_global_config(isolated_home: Path):
    answers = SetupAnswers(
        provider="custom-llamacpp",
        base_url="http://localhost:8080/v1",
        api_key_env="FORGEX_LLAMACPP_KEY",
        api_key="sk-local-secret",
        models={"architect": "qwen2.5:14b"},
        sandbox_enabled=True,
        approval_mode="auto",
    )
    apply_setup(answers, global_dir=isolated_home / ".forgex")

    config = load_config()  # reads ~/.forgex/config.toml (isolated HOME)
    assert config.providers["custom-llamacpp"].base_url == "http://localhost:8080/v1"
    assert config.providers["custom-llamacpp"].api_key_env == "FORGEX_LLAMACPP_KEY"
    assert config.models.architect.provider == "custom-llamacpp"
    assert config.models.architect.model == "qwen2.5:14b"
    assert config.sandbox.enabled is True
    assert config.permissions.mode == "auto"

    env_file = isolated_home / ".forgex" / ".env"
    assert "FORGEX_LLAMACPP_KEY=sk-local-secret" in env_file.read_text(encoding="utf-8")
    if sys.platform != "win32":
        assert (env_file.stat().st_mode & 0o777) == 0o600


def test_setup_cli_end_to_end(tmp_path: Path, monkeypatch, isolated_home):
    from typer.testing import CliRunner

    from forgex.cli.app import app

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("rich.prompt.Prompt.ask", lambda prompt, **kw: kw.get("default", "groq") or "groq")
    monkeypatch.setattr("rich.prompt.Confirm.ask", lambda prompt, **kw: False)
    runner = CliRunner()
    result = runner.invoke(app, ["config", "setup"])
    assert result.exit_code == 0, result.output
    config = load_config()
    assert config.models.architect.provider == "groq"
    assert config.models.architect.model == "llama-3.3-70b-versatile"
    assert config.models.supervisor.model == "llama-3.3-70b-versatile"
