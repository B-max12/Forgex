"""Local model provider — any local OpenAI-compatible server."""

from __future__ import annotations

from forgex.models.openai_compatible import OpenAICompatibleProvider


class LocalProvider(OpenAICompatibleProvider):
    def __init__(self, *, base_url: str, api_key: str | None = None, **kwargs) -> None:
        super().__init__("local", base_url=base_url, api_key=api_key, **kwargs)
