from __future__ import annotations

from pathlib import Path

import pytest

from forgex.config import load_config
from forgex.config.loader import set_config_value
from forgex.schemas.error import ConfigError


def test_defaults(isolated_home):
    cfg = load_config()
    assert cfg.workflow.max_iterations == 5
    assert cfg.permissions.mode == "ask"
    assert cfg.providers["groq"].api_key_env == "FORGEX_GROQ_API_KEY"


def test_project_overrides_global(isolated_home, tmp_path: Path):
    gdir = isolated_home / ".forgex"
    gdir.mkdir()
    (gdir / "config.toml").write_text("[workflow]\nmax_iterations = 3\n")
    proj = tmp_path / "proj" / ".forgex"
    proj.mkdir(parents=True)
    (proj / "config.toml").write_text("[workflow]\nmax_iterations = 7\n")
    assert load_config(tmp_path / "proj").workflow.max_iterations == 7


def test_invalid_value_raises(isolated_home, tmp_path: Path):
    pdir = tmp_path / "p" / ".forgex"
    pdir.mkdir(parents=True)
    (pdir / "config.toml").write_text('[workflow]\nmax_iterations = "nope"\n')
    with pytest.raises(ConfigError):
        load_config(tmp_path / "p")


def test_unknown_key_rejected(isolated_home, tmp_path: Path):
    pdir = tmp_path / "p" / ".forgex"
    pdir.mkdir(parents=True)
    (pdir / "config.toml").write_text("[workflog]\nmax_iterations = 3\n")  # typo
    with pytest.raises(ConfigError):
        load_config(tmp_path / "p")


def test_set_config_value_roundtrip(isolated_home, tmp_path: Path):
    path = tmp_path / ".forgex" / "config.toml"
    set_config_value(path, "models.architect.model", "llama-3.3-70b-versatile")
    set_config_value(path, "workflow.max_iterations", "8")
    set_config_value(path, "sandbox.enabled", "true")
    cfg = load_config(tmp_path)
    assert cfg.models.architect.model == "llama-3.3-70b-versatile"
    assert cfg.workflow.max_iterations == 8
    assert cfg.sandbox.enabled is True


def test_set_invalid_value_refused(isolated_home, tmp_path: Path):
    path = tmp_path / ".forgex" / "config.toml"
    with pytest.raises(ConfigError):
        set_config_value(path, "workflow.max_iterations", "999")
    assert not path.exists()  # nothing written on validation failure


def test_set_config_value_json_list(isolated_home, tmp_path):
    path = tmp_path / ".forgex" / "config.toml"
    set_config_value(path, "fallback.providers", '["openai_compatible"]')
    assert load_config(tmp_path).fallback.providers == ["openai_compatible"]
