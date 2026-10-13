"""OpenAI-compatible chat-completions adapter.

Works with any server implementing POST /chat/completions and GET /models
(OpenAI, Groq, llama.cpp, Ollama, vLLM, LM Studio, ...).
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from forgex.models.base import (
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ModelUsage,
    ProviderHealth,
    ToolCall,
)
from forgex.orchestration.retry import RetryPolicy, run_with_retries
from forgex.schemas.error import AuthenticationError, ProviderError, RateLimitError
from forgex.utils.redact import redact

logger = logging.getLogger("forgex.models")


def parse_sse_content(line: str) -> str | None:
    """Parse one SSE line: content delta, '' for [DONE], None to skip."""
    if not line.startswith("data:"):
        return None
    data = line[len("data:") :].strip()
    if not data:
        return None
    if data == "[DONE]":
        return ""
    try:
        chunk = json.loads(data)
    except ValueError:
        return None
    choices = chunk.get("choices") or []
    if not choices:
        return None
    content = (choices[0].get("delta") or {}).get("content")
    return content if content else None


class OpenAICompatibleProvider(ModelProvider):
    """Adapter for OpenAI-compatible HTTP APIs."""

    def __init__(
        self,
        name: str,
        *,
        base_url: str,
        api_key: str | None = None,
        timeout_seconds: float = 60.0,
        max_retries: int = 2,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(timeout=timeout_seconds)

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _redact_error(self, message: str) -> str:
        secrets = [self.api_key] if self.api_key else []
        return redact(message, secrets)

    async def generate(self, request: ModelRequest) -> ModelResponse:
        url = f"{self.base_url}/chat/completions"

        messages_payload: list[dict[str, Any]] = []
        if request.system:
            messages_payload.append({"role": "system", "content": request.system})

        for msg in request.messages:
            item: dict[str, Any] = {"role": msg.role, "content": msg.content}
            if msg.name:
                item["name"] = msg.name
            if msg.tool_call_id:
                item["tool_call_id"] = msg.tool_call_id
            if msg.tool_calls:
                item["tool_calls"] = msg.tool_calls
            messages_payload.append(item)

        body: dict[str, Any] = {
            "model": request.model,
            "messages": messages_payload,
        }

        if request.tools:
            body["tools"] = request.tools
            body["tool_choice"] = request.tool_choice or "auto"
        if request.response_format:
            body["response_format"] = request.response_format
        if request.temperature is not None:
            body["temperature"] = request.temperature
        if request.max_tokens is not None:
            body["max_tokens"] = request.max_tokens

        async def _call() -> httpx.Response:
            try:
                resp = await self._client.post(url, headers=self._headers(), json=body)
            except httpx.TimeoutException as exc:
                msg = self._redact_error(f"Timeout calling {self.name}: {exc}")
                raise ProviderError(msg, retryable=True) from exc
            except httpx.NetworkError as exc:
                msg = self._redact_error(f"Network error calling {self.name}: {exc}")
                raise ProviderError(msg, retryable=True) from exc
            except OSError as exc:
                msg = self._redact_error(f"Connection error calling {self.name}: {exc}")
                raise ProviderError(msg, retryable=True) from exc

            if resp.status_code in (401, 403):
                msg = self._redact_error(f"Authentication failed for {self.name}: {resp.text}")
                raise AuthenticationError(msg)
            elif resp.status_code == 429:
                msg = self._redact_error(f"Rate limited by {self.name}: {resp.text}")
                raise RateLimitError(msg)
            elif resp.status_code >= 500:
                msg = self._redact_error(f"Server error from {self.name} ({resp.status_code}): {resp.text}")
                raise ProviderError(msg, retryable=True)
            elif resp.status_code != 200:
                msg = self._redact_error(f"Error from {self.name} ({resp.status_code}): {resp.text}")
                raise ProviderError(msg, retryable=False)

            return resp

        policy = RetryPolicy(max_attempts=self.max_retries + 1, initial_delay=1.0)
        try:
            http_resp, attempts = await run_with_retries(_call, policy=policy)
        except ProviderError as exc:
            exc.attempts = getattr(exc, "attempts", 1)
            raise

        data = http_resp.json()
        choices = data.get("choices") or []
        first_choice = choices[0] if choices else {}
        message_data = first_choice.get("message") or {}

        content = message_data.get("content")

        # Parse tool calls
        tool_calls: list[ToolCall] = []
        raw_tcs = message_data.get("tool_calls") or []
        for raw_tc in raw_tcs:
            fn = raw_tc.get("function") or {}
            tool_calls.append(
                ToolCall(
                    id=raw_tc.get("id", ""),
                    name=fn.get("name", ""),
                    arguments=fn.get("arguments", ""),
                )
            )

        # Parse usage
        usage_data = data.get("usage")
        usage = None
        if usage_data:
            usage = ModelUsage(
                prompt_tokens=usage_data.get("prompt_tokens"),
                completion_tokens=usage_data.get("completion_tokens"),
                total_tokens=usage_data.get("total_tokens"),
            )

        return ModelResponse(
            content=content,
            model=data.get("model", request.model),
            provider=self.name,
            usage=usage,
            attempts=attempts,
            tool_calls=tool_calls,
        )

    async def stream(self, request: ModelRequest) -> AsyncIterator[str]:
        url = f"{self.base_url}/chat/completions"

        messages_payload: list[dict[str, Any]] = []
        if request.system:
            messages_payload.append({"role": "system", "content": request.system})
        for msg in request.messages:
            messages_payload.append({"role": msg.role, "content": msg.content})

        body: dict[str, Any] = {
            "model": request.model,
            "messages": messages_payload,
            "stream": True,
        }
        if request.temperature is not None:
            body["temperature"] = request.temperature

        async with self._client.stream("POST", url, headers=self._headers(), json=body) as response:
            if response.status_code != 200:
                text = await response.aread()
                err_msg = self._redact_error(f"Stream error {response.status_code}: {text.decode('utf-8', 'replace')}")
                raise ProviderError(err_msg)
            async for line in response.aiter_lines():
                content = parse_sse_content(line)
                if content:
                    yield content

    async def health(self) -> ProviderHealth:
        start = time.perf_counter()
        try:
            url = f"{self.base_url}/models"
            resp = await self._client.get(url, headers=self._headers(), timeout=10.0)
            latency = (time.perf_counter() - start) * 1000
            if resp.status_code == 200:
                return ProviderHealth(provider=self.name, ok=True, detail="available", latency_ms=latency)
            msg = self._redact_error(f"HTTP {resp.status_code}")
            return ProviderHealth(provider=self.name, ok=False, detail=msg, latency_ms=latency)
        except Exception as exc:  # noqa: BLE001
            latency = (time.perf_counter() - start) * 1000
            msg = self._redact_error(str(exc))
            return ProviderHealth(provider=self.name, ok=False, detail=msg, latency_ms=latency)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
