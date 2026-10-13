"""Model router (spec sections 13, 14, 30, 31).

Agents ask the router — never a provider SDK. The router:
  * resolves the provider+model binding for an agent role from config
  * adapts requests to model capabilities (drops unsupported fields)
  * applies provider fallback (spec 30) after retries are exhausted
  * records usage for observability (spec sections 40, 41)
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any

from forgex.config.schema import ForgexConfig, ProviderConfig
from forgex.models.base import (
    Message,
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ProviderHealth,
)
from forgex.models.capabilities import ModelCapabilities
from forgex.models.factory import build_provider
from forgex.models.registry import ModelRegistry
from forgex.schemas.error import ConfigError, ProviderError
from forgex.schemas.result import ModelUsageRecord
from forgex.storage.repositories import ModelUsageRepository

logger = logging.getLogger("forgex.models.router")


@dataclass
class ModelBinding:
    agent: str
    provider_name: str
    model: str
    provider: ModelProvider
    capabilities: ModelCapabilities


class ModelRouter:
    def __init__(
        self,
        config: ForgexConfig,
        *,
        usage: ModelUsageRepository | None = None,
        provider_builder: Callable[[str, ProviderConfig], ModelProvider] = build_provider,
    ) -> None:
        self._config = config
        self._usage = usage
        self._builder = provider_builder
        self._registry = ModelRegistry(config.models.capabilities)
        self._providers: dict[str, ModelProvider] = {}

    def _provider(self, name: str) -> ModelProvider:
        if name not in self._providers:
            cfg = self._config.providers.get(name)
            if cfg is None:
                raise ConfigError(f"Provider '{name}' not found in configuration")
            self._providers[name] = self._builder(name, cfg)
        return self._providers[name]

    def _resolve_binding(self, agent: str) -> ModelBinding:
        models_cfg = self._config.models
        binding_cfg = getattr(models_cfg, agent, None)
        if binding_cfg is None:
            raise ConfigError(f"No model binding configured for agent role '{agent}'")

        prov_name = binding_cfg.provider
        prov_cfg = self._config.providers.get(prov_name)
        if prov_cfg is None:
            raise ConfigError(f"Provider '{prov_name}' specified for '{agent}' does not exist")

        model_name = binding_cfg.model or prov_cfg.default_model
        if not model_name:
            raise ConfigError(f"No model specified for agent '{agent}' and provider '{prov_name}' has no default_model")

        caps = self._registry.lookup(model_name)
        return ModelBinding(
            agent=agent,
            provider_name=prov_name,
            model=model_name,
            provider=self._provider(prov_name),
            capabilities=caps,
        )

    def binding_for(self, provider: str, model: str) -> ModelBinding:
        cfg = self._config.providers.get(provider)
        if cfg is None:
            raise ConfigError(f"Unknown provider '{provider}' — check [providers.{provider}] in config")
        resolved_model = model or cfg.default_model
        if not resolved_model:
            raise ConfigError(f"No model for explicit binding on provider '{provider}'")
        return ModelBinding(
            agent="explicit",
            provider_name=provider,
            model=resolved_model,
            provider=self._provider(provider),
            capabilities=self._registry.lookup(resolved_model),
        )

    def capabilities_for(self, agent: str) -> ModelCapabilities:
        return self._resolve_binding(agent).capabilities

    def capabilities_for_binding(self, provider: str, model: str) -> ModelCapabilities:
        return self.binding_for(provider, model).capabilities

    def _build_request(
        self,
        binding: ModelBinding,
        messages: list[Message],
        *,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        response_format: dict[str, str] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ModelRequest:
        adapted_tools = tools if binding.capabilities.supports_tools else None
        adapted_rf = response_format if binding.capabilities.supports_json else None

        return ModelRequest(
            model=binding.model,
            messages=messages,
            system=system,
            tools=adapted_tools,
            tool_choice=tool_choice if adapted_tools else None,
            response_format=adapted_rf,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def _record(
        self,
        binding: ModelBinding,
        *,
        run_id: str | None = None,
        latency_ms: float | None = None,
        response: ModelResponse | None = None,
        error: str | None = None,
        attempts: int = 1,
    ) -> None:
        if self._usage is None:
            return
        rec = ModelUsageRecord(
            run_id=run_id,
            agent=binding.agent,
            provider=binding.provider_name,
            model=binding.model,
            input_tokens=response.usage.input_tokens if response and response.usage else None,
            output_tokens=response.usage.output_tokens if response and response.usage else None,
            total_tokens=response.usage.total_tokens if response and response.usage else None,
            latency_ms=latency_ms,
            attempts=attempts,
            success=error is None,
            error=error,
        )
        try:
            self._usage.insert(rec)
        except Exception:
            logger.warning("Failed to record model usage", exc_info=True)

    async def generate(
        self,
        agent: str,
        *,
        messages: list[Message],
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        response_format: dict[str, str] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        run_id: str | None = None,
    ) -> ModelResponse:
        primary = self._resolve_binding(agent)
        req = self._build_request(
            primary,
            messages,
            system=system,
            tools=tools,
            tool_choice=tool_choice,
            response_format=response_format,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        start = time.perf_counter()
        try:
            resp = await primary.provider.generate(req)
            self._record(primary, run_id=run_id, latency_ms=(time.perf_counter() - start) * 1000, response=resp, attempts=resp.attempts)
            return resp
        except Exception as primary_exc:
            latency = (time.perf_counter() - start) * 1000
            self._record(primary, run_id=run_id, latency_ms=latency, error=f"{type(primary_exc).__name__}: {primary_exc}", attempts=getattr(primary_exc, "attempts", 1))

            # Fallback chain (§30)
            if self._config.fallback.enabled and self._config.fallback.providers:
                for fb_name in self._config.fallback.providers:
                    if fb_name == primary.provider_name:
                        continue
                    fb_cfg = self._config.providers.get(fb_name)
                    if not fb_cfg or not fb_cfg.default_model:
                        continue
                    fb_binding = ModelBinding(
                        agent=agent,
                        provider_name=fb_name,
                        model=fb_cfg.default_model,
                        provider=self._provider(fb_name),
                        capabilities=self._registry.lookup(fb_cfg.default_model),
                    )
                    fb_req = self._build_request(
                        fb_binding,
                        messages,
                        system=system,
                        tools=tools,
                        tool_choice=tool_choice,
                        response_format=response_format,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                    fb_start = time.perf_counter()
                    try:
                        logger.warning("Primary provider %s failed; falling back to %s", primary.provider_name, fb_name)
                        fb_resp = await fb_binding.provider.generate(fb_req)
                        self._record(fb_binding, run_id=run_id, latency_ms=(time.perf_counter() - fb_start) * 1000, response=fb_resp, attempts=fb_resp.attempts)
                        return fb_resp
                    except Exception as fb_exc:
                        self._record(fb_binding, run_id=run_id, latency_ms=(time.perf_counter() - fb_start) * 1000, error=f"{type(fb_exc).__name__}: {fb_exc}", attempts=getattr(fb_exc, "attempts", 1))
                        continue

            raise primary_exc

    async def generate_with(
        self,
        *,
        provider: str,
        model: str,
        agent: str,
        messages: list[Message],
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        response_format: dict[str, str] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        run_id: str | None = None,
    ) -> ModelResponse:
        """Generate against an EXPLICIT provider/model binding with NO fallback."""
        binding = self.binding_for(provider, model)
        req = self._build_request(
            binding,
            messages,
            system=system,
            tools=tools,
            tool_choice=tool_choice,
            response_format=response_format,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        start = time.perf_counter()
        try:
            resp = await binding.provider.generate(req)
            self._record(binding, run_id=run_id, latency_ms=(time.perf_counter() - start) * 1000, response=resp, attempts=resp.attempts)
            return resp
        except Exception as exc:
            self._record(binding, run_id=run_id, latency_ms=(time.perf_counter() - start) * 1000, error=f"{type(exc).__name__}: {exc}", attempts=getattr(exc, "attempts", 1))
            raise

    async def stream(
        self,
        agent: str,
        *,
        messages: list[Message],
        system: str | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[str]:
        binding = self._resolve_binding(agent)
        req = ModelRequest(
            model=binding.model,
            messages=messages,
            system=system,
            temperature=temperature,
        )
        async for chunk in binding.provider.stream(req):
            yield chunk

    def health_all(self) -> dict[str, ProviderHealth]:
        results: dict[str, ProviderHealth] = {}
        for name in self._config.providers:
            try:
                prov = self._provider(name)
                # Run async health in an event loop or thread
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None
                if loop and loop.is_running():
                    import concurrent.futures

                    def _run_health(p: ModelProvider = prov) -> ProviderHealth:
                        return asyncio.run(p.health())

                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        health = pool.submit(_run_health).result()
                else:
                    health = asyncio.run(prov.health())
                results[name] = health
            except (ConfigError, ProviderError) as exc:
                results[name] = ProviderHealth(provider=name, ok=False, detail=str(exc))
            except Exception as exc:  # noqa: BLE001
                results[name] = ProviderHealth(provider=name, ok=False, detail=str(exc))
        return results

    async def aclose(self) -> None:
        for p in self._providers.values():
            await p.aclose()
        self._providers.clear()


def collect_health(config: ForgexConfig) -> dict[str, ProviderHealth]:
    router = ModelRouter(config)
    try:
        return router.health_all()
    finally:
        asyncio.run(router.aclose())
