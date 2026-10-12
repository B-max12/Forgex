from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from forgex import __version__  # noqa: F401  (ensures package import works)
from forgex.cli.app import app

runner = CliRunner()


def test_models_show_json(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["init"])
    result = runner.invoke(app, ["models", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    roles = {b["agent"] for b in payload["bindings"]}
    assert roles == {"architect", "builder", "expert_coder", "supervisor"}


def test_models_catalog(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["init"])
    result = runner.invoke(app, ["models", "catalog", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert any(c["model"] == "llama-3.3-70b-versatile" for c in payload["catalog"])


def test_models_health_with_fake_providers(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["init"])
    from forgex.cli.commands import models as models_cmd
    from forgex.models.base import ProviderHealth

    def fake_collect(config):
        return {
            "groq": ProviderHealth(provider="groq", ok=True, detail="fake-ok", latency_ms=1.0),
            "local": ProviderHealth(provider="local", ok=False, detail="not configured"),
        }

    monkeypatch.setattr(models_cmd, "collect_health", fake_collect)
    result = runner.invoke(app, ["models", "health", "--json"])
    assert result.exit_code == 1  # local is down → nonzero
    payload = json.loads(result.output)
    assert payload["providers"]["groq"]["ok"] is True
    assert payload["providers"]["local"]["ok"] is False
