from __future__ import annotations

import os
import sys
from pathlib import Path

from forgex.config.loader import load_env_files, parse_env_file, store_secret


def test_parse_env_file(tmp_path: Path):
    env = tmp_path / ".env"
    env.write_text(
        "# comment\nexport A=\"quoted\"\nB=plain\ninvalidline\nC='single'\n", encoding="utf-8"
    )
    assert parse_env_file(env) == {"A": "quoted", "B": "plain", "C": "single"}


def test_load_env_files_priority(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    (home / ".forgex").mkdir(parents=True)
    (home / ".forgex" / ".env").write_text("FX_KEY=global\nFX_OTHER=1\n", encoding="utf-8")
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / ".env").write_text("FX_KEY=project\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    if sys.platform == "win32":
        monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("FX_KEY", raising=False)
    monkeypatch.delenv("FX_OTHER", raising=False)

    load_env_files(proj)
    assert os.environ["FX_KEY"] == "project"  # project beats global
    assert os.environ["FX_OTHER"] == "1"

    monkeypatch.setenv("FX_KEY", "real")
    load_env_files(proj)
    assert os.environ["FX_KEY"] == "real"  # real environment always wins


def test_store_secret_roundtrip(tmp_path: Path):
    store_secret("FX_SECRET", "v1", global_dir=tmp_path)
    assert (tmp_path / ".env").read_text(encoding="utf-8") == "FX_SECRET=v1\n"
    store_secret("FX_SECRET", "v2", global_dir=tmp_path)
    store_secret("FX_OTHER", "x", global_dir=tmp_path)
    content = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "FX_SECRET=v2" in content and "FX_OTHER=x" in content
    if sys.platform != "win32":
        assert ((tmp_path / ".env").stat().st_mode & 0o777) == 0o600
