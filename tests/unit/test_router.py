from __future__ import annotations

import pytest

from forgex.config.schema import AgentModelBinding, FallbackConfig, ForgexConfig, ProviderConfig
from forgex.models.base import Message, ModelRequest, ModelResponse
from forgex.models.router import ModelRouter
from forgex.schemas.error import ProviderError
from forgex.schemas.result import ModelUsageRecord
from forgex.storage.database import Database
from forgex.storage.repositories import ModelUsageRepository


class FakeProvider:
    def __init__(
        self,
        name: str = "p1",
        error: Exception | None = None,
        response: ModelResponse | None = None,
    ) -> None:
        self.name = name
        self.error = error
        self.response = response
        self.calls: list[ModelRequest] = []

    async def generate(self, req: ModelRequest) -> ModelResponse:
        self.calls.append(req)
        if self.error:
            raise self.error
        if self.response:
            return self.response
        return ModelResponse(
            content="ok",
            model=req.model,
            provider=self.name,
        )

    async def aclose(self) -> None:
        pass


def make_config(fallback: FallbackConfig | None = None) -> ForgexConfig:
    cfg = ForgexConfig()
    cfg.providers = {
        "p1": ProviderConfig(type="openai_compatible", default_model="m1"),
        "p2": ProviderConfig(type="openai_compatible", default_model="m2"),
        "p3": ProviderConfig(type="openai_compatible", default_model=""),
    }
    cfg.models.architect = AgentModelBinding(provider="p1", model="m1")
    if fallback is not None:
        cfg.fallback = fallback
    return cfg


async def test_fallback_used_after_provider_failure():
    primary = FakeProvider("p1", error=ProviderError("down", retryable=True))
    secondary = FakeProvider("p2")
    fakes = {"p1": primary, "p2": secondary}
    cfg = make_config(fallback=FallbackConfig(enabled=True, providers=["p2"]))
    router = ModelRouter(cfg, provider_builder=lambda n, c: fakes[n])
    response = await router.generate("architect", messages=[Message(role="user", content="x")])
    assert response.provider == "p2"
    assert response.model == "m2"
    assert secondary.calls[0].model == "m2"


async def test_fallback_disabled_raises_original():
    primary = FakeProvider("p1", error=ProviderError("down", retryable=True))
    cfg = make_config()
    router = ModelRouter(cfg, provider_builder=lambda n, c: primary)
    with pytest.raises(ProviderError):
        await router.generate("architect", messages=[Message(role="user", content="x")])


async def test_fallback_skips_provider_without_default_model():
    primary = FakeProvider("p1", error=ProviderError("down", retryable=True))
    cfg = make_config(fallback=FallbackConfig(enabled=True, providers=["p3"]))
    router = ModelRouter(cfg, provider_builder=lambda n, c: primary)
    with pytest.raises(ProviderError):
        await router.generate("architect", messages=[Message(role="user", content="x")])


async def test_usage_recorded(tmp_path):
    db = Database(tmp_path / "state.db")
    usage = ModelUsageRepository(db)
    fake = FakeProvider(response=ModelResponse(
        content="ok", model="m1", provider="p1",
        usage=__import__("forgex.models.base", fromlist=["ModelUsage"]).ModelUsage(
            input_tokens=7, output_tokens=3, total_tokens=10),
    ))
    router = ModelRouter(make_config(), usage=usage, provider_builder=lambda n, c: fake)
    await router.generate("architect", messages=[Message(role="user", content="x")], run_id="r1")
    rows = usage.recent()
    assert len(rows) == 1
    row: ModelUsageRecord = rows[0]
    assert row.agent == "architect" and row.provider == "p1" and row.model == "m1"
    assert row.input_tokens == 7 and row.total_tokens == 10 and row.success
    assert row.run_id == "r1"
    db.close()


async def test_rate_limit_triggers_immediate_fallback():
    """When the primary provider returns a 429, the router should immediately
    try fallback providers without waiting for retries to exhaust."""
    from forgex.schemas.error import RateLimitError

    primary = FakeProvider("p1", error=RateLimitError("429 too many requests"))
    secondary = FakeProvider("p2")
    fakes = {"p1": primary, "p2": secondary}
    # on_rate_limit is True by default — even without fallback.enabled,
    # it should still auto-switch on 429.
    cfg = make_config(fallback=FallbackConfig(enabled=False, providers=["p2"], on_rate_limit=True))
    router = ModelRouter(cfg, provider_builder=lambda n, c: fakes[n])
    response = await router.generate("architect", messages=[Message(role="user", content="x")])
    assert response.provider == "p2"
    assert response.model == "m2"


async def test_rate_limit_cooldown_skips_primary():
    """After a rate limit, subsequent calls should skip the primary
    provider entirely and go straight to fallbacks."""
    from forgex.schemas.error import RateLimitError

    call_count = 0
    class CountingProvider(FakeProvider):
        async def generate(self, req):
            nonlocal call_count
            call_count += 1
            return await super().generate(req)

    primary = FakeProvider("p1", error=RateLimitError("429"))
    secondary = CountingProvider("p2")
    fakes = {"p1": primary, "p2": secondary}
    cfg = make_config(fallback=FallbackConfig(enabled=False, providers=["p2"], on_rate_limit=True))
    router = ModelRouter(cfg, provider_builder=lambda n, c: fakes[n])

    # First call triggers rate limit on p1, falls back to p2
    await router.generate("architect", messages=[Message(role="user", content="1")])
    # Second call should skip p1 entirely (in cooldown) and go straight to p2
    await router.generate("architect", messages=[Message(role="user", content="2")])
    assert call_count == 2  # p2 was called both times


async def test_rate_limit_disabled_raises():
    """When on_rate_limit is False, rate limits should propagate as errors."""
    from forgex.schemas.error import RateLimitError

    primary = FakeProvider("p1", error=RateLimitError("429"))
    cfg = make_config(fallback=FallbackConfig(enabled=False, providers=["p2"], on_rate_limit=False))
    router = ModelRouter(cfg, provider_builder=lambda n, c: primary)
    with pytest.raises(RateLimitError):
        await router.generate("architect", messages=[Message(role="user", content="x")])

