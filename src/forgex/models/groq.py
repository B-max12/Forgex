"""Groq adapter — the OpenAI-compatible protocol with Groq defaults."""

from __future__ import annotations

from forgex.models.openai_compatible import OpenAICompatibleProvider

DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_API_KEY_ENV = "FORGEX_GROQ_API_KEY"


class GroqProvider(OpenAICompatibleProvider):
    def __init__(self, *, base_url: str | None = None, api_key: str | None = None, **kwargs) -> None:
        super().__init__("groq", base_url=base_url or DEFAULT_BASE_URL, api_key=api_key, **kwargs)
