import json
import os

import pytest
from typer.testing import CliRunner

from forgex.cli.app import app
from forgex.config import load_config
from forgex.config.schema import ProviderConfig
from forgex.models.factory import build_provider
from forgex.schemas.error import ConfigError, ProviderError

runner = CliRunner()


def test_offline_disables_research(monkeypatch):
    monkeypatch.setenv("FORGEX_OFFLINE", "1")
    assert load_config().research.enabled is False


def test_online_default_keeps_research(monkeypatch):
    monkeypatch.delenv("FORGEX_OFFLINE", raising=False)
    assert load_config().research.enabled is True


def test_offline_blocks_remote_providers_local_allowed(monkeypatch):
    monkeypatch.setenv("FORGEX_OFFLINE", "1")
    with pytest.raises(ProviderError, match="offline"):
        build_provider("groq", ProviderConfig(type="groq",
                                              base_url="https://x/v1"))
    # local passes the gate (fails later on missing base_url — proving the
    # offline gate itself did not block it)
    with pytest.raises(ConfigError, match="base_url"):
        build_provider("local", ProviderConfig(type="local"))


def test_offline_cli_flag_flows_into_config(tmp_path, monkeypatch):
    monkeypatch.delenv("FORGEX_OFFLINE", raising=False)
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["init"])
    try:
        result = runner.invoke(app, ["--offline", "config", "show", "--json"])
        assert result.exit_code == 0, result.output
        assert json.loads(result.output)["research"]["enabled"] is False
    finally:
        os.environ.pop("FORGEX_OFFLINE", None)
