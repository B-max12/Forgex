"""Provider factory: config → provider instance (spec sections 13, 26, 46, 73)."""

from __future__ import annotations

import os
from typing import Any

from forgex.config.schema import ForgexConfig, ProviderConfig
from forgex.models.base import ModelProvider
from forgex.models.groq import DEFAULT_API_KEY_ENV as GROQ_KEY_ENV
from forgex.models.groq import DEFAULT_BASE_URL as GROQ_BASE_URL
from forgex.models.groq import GroqProvider
from forgex.models.local import LocalProvider
from forgex.models.openai_compatible import OpenAICompatibleProvider
from forgex.schemas.error import ConfigError, ProviderError


def resolve_api_key(config: ProviderConfig) -> str | None:
    env_name = config.api_key_env
    if env_name is None and config.type == "groq":
        env_name = GROQ_KEY_ENV
    if not env_name:
        return None
    return os.environ.get(env_name) or None


def build_provider(
    name: str,
    config: ProviderConfig,
    *,
    http_client: Any = None,
) -> ModelProvider:
    """Build the provider instance for a configured provider entry."""
    if os.environ.get("FORGEX_OFFLINE") == "1" and config.type != "local":
        msg = (
            f"offline mode: remote provider '{name}' is disabled "
            "(--offline / FORGEX_OFFLINE=1) — configure a local provider"
        )
        raise ProviderError(msg)

    kwargs: dict[str, Any] = {
        "api_key": resolve_api_key(config),
        "timeout_seconds": config.timeout_seconds,
        "max_retries": config.max_retries,
    }
    if http_client is not None:
        kwargs["http_client"] = http_client

    if config.type == "groq":
        return GroqProvider(base_url=config.base_url or GROQ_BASE_URL, **kwargs)
    if config.type == "local":
        if not config.base_url:
            msg = (
                f"Provider '{name}' (local) needs a base_url, "
                "e.g. http://localhost:11434/v1"
            )
            raise ConfigError(msg)
        return LocalProvider(base_url=config.base_url, **kwargs)
    if not config.base_url:
        msg = f"Provider '{name}' (openai_compatible) needs a base_url"
        raise ConfigError(msg)
    return OpenAICompatibleProvider(name, base_url=config.base_url, **kwargs)


def provider_names(config: ForgexConfig) -> list[str]:
    return sorted(config.providers)
