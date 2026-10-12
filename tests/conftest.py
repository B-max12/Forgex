"""Shared fixtures. Every test runs with an isolated HOME so the user's real
~/.forgex is never read or written, and no real credentials leak in."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: "pytest.TempPathFactory", monkeypatch: pytest.MonkeyPatch):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))  # Windows
    monkeypatch.delenv("FORGEX_GROQ_API_KEY", raising=False)
    monkeypatch.delenv("FORGEX_OPENAI_API_KEY", raising=False)
    return home
