"""Model router (spec sections 13, 14, 30, 31).

Agents ask the router — never a provider SDK. The router:
  * resolves the provider+model binding for an agent role from config
  * adapts requests to model capabilities (drops unsupported fields)
  * applies provider fallback (spec 30) after retries are exhausted
  * automatically switches to fallback providers on rate limits (429)
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
from forgex.schemas.error import (
    ConfigError,
    ContextLengthExceededError,
    ProviderError,
    RateLimitError,
)
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
        # Rate-limit tracking: provider_name -> timestamp when cooldown expires
        self._rate_limited_until: dict[str, float] = {}

    def _provider(self, name: str) -> ModelProvider:
        if name not in self._providers:
            cfg = self._config.providers.get(name)
            if cfg is None:
                raise ConfigError(f"Provider '{name}' not found in configuration")
            self._providers[name] = self._builder(name, cfg)
        return self._providers[name]

    def _mark_rate_limited(self, provider_name: str) -> None:
        """Record that a provider is rate-limited; skip it until cooldown expires."""
        cooldown = self._config.fallback.cooldown_seconds
        until = time.monotonic() + cooldown
        self._rate_limited_until[provider_name] = until
        logger.warning(
            "Provider %s rate-limited — cooling down for %ds",
            provider_name,
            cooldown,
        )

    def _is_rate_limited(self, provider_name: str) -> bool:
        """Return True if the provider is still in cooldown."""
        until = self._rate_limited_until.get(provider_name)
        if until is None:
            return False
        if time.monotonic() >= until:
            # Cooldown expired — allow again
            del self._rate_limited_until[provider_name]
            logger.info("Provider %s cooldown expired — re-enabling", provider_name)
            return False
        return True

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

    def _fallback_candidates(self, *, skip_provider: str) -> list[ModelBinding]:
        """Return a list of fallback bindings, skipping the given provider
        and any providers that are currently rate-limited / in cooldown."""
        candidates: list[ModelBinding] = []
        provider_names = (
            self._config.fallback.providers
            if self._config.fallback.providers
            else list(self._config.providers.keys())
        )
        for fb_name in provider_names:
            if fb_name == skip_provider:
                continue
            if self._is_rate_limited(fb_name):
                logger.debug("Skipping fallback %s — still in cooldown", fb_name)
                continue
            fb_cfg = self._config.providers.get(fb_name)
            if not fb_cfg or not fb_cfg.default_model:
                continue
            candidates.append(
                ModelBinding(
                    agent="fallback",
                    provider_name=fb_name,
                    model=fb_cfg.default_model,
                    provider=self._provider(fb_name),
                    capabilities=self._registry.lookup(fb_cfg.default_model),
                )
            )
        return candidates

    async def _try_fallback_chain(
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
        skip_provider: str,
        reason: str = "failed",
    ) -> ModelResponse | None:
        """Try each fallback provider in order. Returns the first successful
        response, or None if all fallbacks fail."""
        candidates = self._fallback_candidates(skip_provider=skip_provider)
        if not candidates:
            return None

        for fb_binding in candidates:
            fb_binding.agent = agent  # Preserve agent role for usage tracking
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
                logger.warning(
                    "Primary provider %s %s; falling back to %s/%s",
                    skip_provider,
                    reason,
                    fb_binding.provider_name,
                    fb_binding.model,
                )
                fb_resp = await fb_binding.provider.generate(fb_req)
                self._record(
                    fb_binding,
                    run_id=run_id,
                    latency_ms=(time.perf_counter() - fb_start) * 1000,
                    response=fb_resp,
                    attempts=fb_resp.attempts,
                )
                return fb_resp
            except RateLimitError:
                self._mark_rate_limited(fb_binding.provider_name)
                self._record(
                    fb_binding,
                    run_id=run_id,
                    latency_ms=(time.perf_counter() - fb_start) * 1000,
                    error="RateLimitError (fallback)",
                    attempts=1,
                )
                continue
            except Exception as fb_exc:
                self._record(
                    fb_binding,
                    run_id=run_id,
                    latency_ms=(time.perf_counter() - fb_start) * 1000,
                    error=f"{type(fb_exc).__name__}: {fb_exc}",
                    attempts=getattr(fb_exc, "attempts", 1),
                )
                continue

        return None

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

        # If the primary provider is still in cooldown from a previous rate
        # limit, skip it entirely and jump straight to fallbacks.
        if self._is_rate_limited(primary.provider_name):
            logger.info(
                "Primary provider %s still in rate-limit cooldown — trying fallbacks",
                primary.provider_name,
            )
            fb_resp = await self._try_fallback_chain(
                agent,
                messages=messages,
                system=system,
                tools=tools,
                tool_choice=tool_choice,
                response_format=response_format,
                temperature=temperature,
                max_tokens=max_tokens,
                run_id=run_id,
                skip_provider=primary.provider_name,
                reason="rate-limited (cooldown)",
            )
            if fb_resp is not None:
                return fb_resp
            # All fallbacks failed too — try primary anyway as last resort
            logger.warning(
                "All fallbacks exhausted; retrying rate-limited primary %s",
                primary.provider_name,
            )

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
            self._record(
                primary,
                run_id=run_id,
                latency_ms=(time.perf_counter() - start) * 1000,
                response=resp,
                attempts=resp.attempts,
            )
            return resp
        except RateLimitError as rate_exc:
            # Rate limit — mark the provider and immediately try fallbacks
            latency = (time.perf_counter() - start) * 1000
            self._record(
                primary,
                run_id=run_id,
                latency_ms=latency,
                error=f"RateLimitError: {rate_exc}",
                attempts=getattr(rate_exc, "attempts", 1),
            )

            if self._config.fallback.on_rate_limit:
                self._mark_rate_limited(primary.provider_name)
                fb_resp = await self._try_fallback_chain(
                    agent,
                    messages=messages,
                    system=system,
                    tools=tools,
                    tool_choice=tool_choice,
                    response_format=response_format,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    run_id=run_id,
                    skip_provider=primary.provider_name,
                    reason="rate-limited (429)",
                )
                if fb_resp is not None:
                    return fb_resp

            raise rate_exc

        except ContextLengthExceededError as ctx_exc:
            # Context too long — no point falling back with same oversized prompt
            latency = (time.perf_counter() - start) * 1000
            self._record(
                primary,
                run_id=run_id,
                latency_ms=latency,
                error=f"ContextLengthExceeded: {ctx_exc}",
                attempts=1,
            )
            logger.error(
                "Context length exceeded on %s/%s — cannot fall back",
                primary.provider_name,
                primary.model,
            )
            raise ctx_exc

        except Exception as primary_exc:
            latency = (time.perf_counter() - start) * 1000
            self._record(
                primary,
                run_id=run_id,
                latency_ms=latency,
                error=f"{type(primary_exc).__name__}: {primary_exc}",
                attempts=getattr(primary_exc, "attempts", 1),
            )

            # General fallback chain (§30)
            if self._config.fallback.enabled and self._config.fallback.providers:
                fb_resp = await self._try_fallback_chain(
                    agent,
                    messages=messages,
                    system=system,
                    tools=tools,
                    tool_choice=tool_choice,
                    response_format=response_format,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    run_id=run_id,
                    skip_provider=primary.provider_name,
                    reason=f"error ({type(primary_exc).__name__})",
                )
                if fb_resp is not None:
                    return fb_resp

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
        try:
            async for chunk in binding.provider.stream(req):
                yield chunk
        except Exception as exc:
            logger.error(
                "Streaming failed on %s/%s for agent '%s': %s",
                binding.provider_name,
                binding.model,
                agent,
                exc,
                exc_info=True,
            )
            raise

    async def health_all_async(self) -> dict[str, ProviderHealth]:
        """Asynchronously query health for all configured providers without thread pools."""
        results: dict[str, ProviderHealth] = {}
        for name in self._config.providers:
            try:
                prov = self._provider(name)
                results[name] = await prov.health()
            except (ConfigError, ProviderError) as exc:
                results[name] = ProviderHealth(provider=name, ok=False, detail=str(exc))
            except Exception as exc:  # noqa: BLE001
                results[name] = ProviderHealth(provider=name, ok=False, detail=str(exc))
        return results

    def health_all(self) -> dict[str, ProviderHealth]:
        results: dict[str, ProviderHealth] = {}
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(lambda: asyncio.run(self.health_all_async())).result()
        return asyncio.run(self.health_all_async())

    async def aclose(self) -> None:
        for p in self._providers.values():
            await p.aclose()
        self._providers.clear()


async def _collect_health_async(config: ForgexConfig) -> dict[str, ProviderHealth]:
    router = ModelRouter(config)
    try:
        return await router.health_all_async()
    finally:
        await router.aclose()


def collect_health(config: ForgexConfig) -> dict[str, ProviderHealth]:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(lambda: asyncio.run(_collect_health_async(config))).result()
    return asyncio.run(_collect_health_async(config))
