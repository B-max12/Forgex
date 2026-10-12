"""Versioned agent prompts (spec section 42)."""

from __future__ import annotations

import importlib.resources

from forgex.schemas.error import ConfigError

PROMPT_VERSIONS: dict[str, str] = {
    "architect": "v1",
    "builder": "v1",
    "expert_coder": "v1",
    "supervisor": "v1",
    "reviewer": "v1",
}


def load_prompt(name: str) -> str:
    if name not in PROMPT_VERSIONS:
        msg = f"Unknown prompt: {name!r} (known: {', '.join(sorted(PROMPT_VERSIONS))})"
        raise ConfigError(msg)
    resource = importlib.resources.files("forgex.prompts") / f"{name}.md"
    return resource.read_text(encoding="utf-8")


def prompt_version(name: str) -> str:
    return f"{name}:{PROMPT_VERSIONS[name]}"
