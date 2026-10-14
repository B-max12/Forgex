"""Model registry (spec sections 14, 31, 65).

The built-in catalog is an ADVISORY snapshot — model IDs go stale. Actual
selection always comes from user configuration; the catalog only informs
capability adaptation.
"""

from __future__ import annotations

from forgex.models.capabilities import ModelCapabilities

_DEFAULT_CATALOG: dict[str, ModelCapabilities] = {
    # Groq models
    "llama-3.3-70b-versatile": ModelCapabilities(
        model="llama-3.3-70b-versatile",
        context_window=131072,
        supports_tools=True,
        supports_json=True,
        supports_streaming=True,
        known=True,
    ),
    "llama-3.1-8b-instant": ModelCapabilities(
        model="llama-3.1-8b-instant",
        context_window=131072,
        supports_tools=True,
        supports_json=True,
        supports_streaming=True,
        known=True,
    ),
    # OpenAI models
    "gpt-4o": ModelCapabilities(
        model="gpt-4o",
        context_window=128000,
        supports_tools=True,
        supports_json=True,
        supports_streaming=True,
        known=True,
    ),
    "gpt-4o-mini": ModelCapabilities(
        model="gpt-4o-mini",
        context_window=128000,
        supports_tools=True,
        supports_json=True,
        supports_streaming=True,
        known=True,
    ),
    "o1-mini": ModelCapabilities(
        model="o1-mini",
        context_window=128000,
        supports_tools=False,
        supports_json=True,
        supports_streaming=False,
        known=True,
    ),
    # Meta Llama models (OpenRouter / Groq / Ollama)
    # NOTE: Llama models via OpenRouter do not reliably produce native
    # tool_calls in the API response — they often emit XML-style markup
    # instead.  Disabling native tools forces the JSON-protocol fallback
    # which works far more reliably with instruction-tuned Llama models.
    "meta-llama/llama-3.3-70b-instruct": ModelCapabilities(
        model="meta-llama/llama-3.3-70b-instruct",
        context_window=131072,
        supports_tools=False,
        supports_json=True,
        supports_streaming=True,
        known=True,
    ),
    "meta-llama/llama-3.1-70b-instruct": ModelCapabilities(
        model="meta-llama/llama-3.1-70b-instruct",
        context_window=131072,
        supports_tools=False,
        supports_json=True,
        supports_streaming=True,
        known=True,
    ),
    "meta-llama/llama-3.1-8b-instruct": ModelCapabilities(
        model="meta-llama/llama-3.1-8b-instruct",
        context_window=131072,
        supports_tools=False,
        supports_json=True,
        supports_streaming=True,
        known=True,
    ),
    "qwen/qwen-2.5-coder-32b-instruct": ModelCapabilities(
        model="qwen/qwen-2.5-coder-32b-instruct",
        context_window=131072,
        supports_tools=True,
        supports_json=True,
        supports_streaming=True,
        known=True,
    ),
}


class ModelRegistry:
    def __init__(self, overrides: dict[str, ModelCapabilities] | None = None) -> None:
        self._catalog = dict(_DEFAULT_CATALOG)
        if overrides:
            for k, cap in overrides.items():
                if not cap.known:
                    cap = cap.model_copy(update={"known": True})
                self._catalog[k] = cap

    def lookup(self, model: str) -> ModelCapabilities:
        clean_model = model.split(":", 1)[-1] if ":" in model else model
        if model in self._catalog:
            return self._catalog[model]
        if clean_model in self._catalog:
            return self._catalog[clean_model]
        # Conservative defaults for unknown models
        return ModelCapabilities(
            model=model,
            context_window=None,
            supports_tools=False,
            supports_json=False,
            supports_streaming=False,
            known=False,
        )

    def catalog(self) -> list[ModelCapabilities]:
        return sorted(self._catalog.values(), key=lambda c: c.model)
