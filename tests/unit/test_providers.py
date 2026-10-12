from __future__ import annotations

import json
import httpx
import pytest

from forgex.config.schema import ProviderConfig
from forgex.models.base import ChatMessage, ModelRequest, ToolCall
from forgex.models.factory import build_provider
from forgex.models.openai_compatible import OpenAICompatibleProvider
from forgex.schemas.error import AuthenticationError, ProviderError, RateLimitError

captured: dict = {}


def req(messages=None) -> ModelRequest:
    return ModelRequest(
        model="m",
        messages=messages or [ChatMessage(role="user", content="hello")],
    )


def make_provider(handler):
    def wrap_handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization", "")
        captured["body"] = json.loads(request.content.decode("utf-8")) if request.content else {}
        return handler(request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(wrap_handler))
    return OpenAICompatibleProvider(
        "test-provider",
        base_url="https://api.example.com/v1",
        api_key="test-key-123",
        http_client=client,
    )


async def test_provider_generate_success():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "model": "m",
            "choices": [{"message": {"role": "assistant", "content": "hello"},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        })

    provider = make_provider(handler)
    response = await provider.generate(req())
    assert response.content == "hello"
    assert response.usage is not None and response.usage.total_tokens == 15
    assert response.attempts == 1
    assert captured["url"].endswith("/chat/completions")
    assert captured["auth"] == "Bearer test-key-123"
    assert captured["body"]["model"] == "m"
    await provider.aclose()


async def test_auth_error_not_retried():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(401, json={"error": {"message": "invalid key"}})

    provider = make_provider(handler)
    with pytest.raises(AuthenticationError):
        await provider.generate(req())
    assert calls["n"] == 1
    await provider.aclose()


async def test_rate_limit_retried_then_succeeds():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={"error": {"message": "rate limit"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    provider = make_provider(handler)
    response = await provider.generate(req())
    assert response.content == "ok"
    assert response.attempts == 2
    assert calls["n"] == 2
    await provider.aclose()


async def test_server_error_exhausts_retries():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500, text="boom")

    provider = make_provider(handler)
    with pytest.raises(ProviderError) as excinfo:
        await provider.generate(req())
    assert excinfo.value.retryable is True
    assert excinfo.value.attempts == 3
    assert calls["n"] == 3
    await provider.aclose()


async def test_error_message_redacts_api_key():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="invalid key test-key-123")

    provider = make_provider(handler)
    with pytest.raises(AuthenticationError) as excinfo:
        await provider.generate(req())
    assert "test-key-123" not in str(excinfo.value)
    await provider.aclose()


async def test_tool_calls_parsed():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "model": "m",
            "choices": [{"message": {
                "role": "assistant",
                "tool_calls": [{"id": "t1", "type": "function", "function": {"name": "f", "arguments": "{}"}}],
            }}],
        })

    provider = make_provider(handler)
    res = await provider.generate(req())
    assert len(res.tool_calls) == 1
    assert res.tool_calls[0].name == "f"
    await provider.aclose()
