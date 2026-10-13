"""Model provider contract (spec section 13).

Agents never touch provider SDKs — they talk to the ModelRouter, which
talks to adapters implementing this ABC.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Message(BaseModel):
    """One chat message (wire format for OpenAI-compatible APIs)."""

    model_config = ConfigDict(extra="forbid")

    role: str  # system | user | assistant | tool
    content: str | None = None
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


ChatMessage = Message


class ToolCall(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = ""
    name: str
    arguments: Any = ""


class ModelUsage(BaseModel):
    """Usage as reported by the provider (None = not reported)."""

    model_config = ConfigDict(extra="ignore")

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None

    def __init__(self, **data: Any) -> None:
        if "input_tokens" in data and "prompt_tokens" not in data:
            data["prompt_tokens"] = data.pop("input_tokens")
        if "output_tokens" in data and "completion_tokens" not in data:
            data["completion_tokens"] = data.pop("output_tokens")
        super().__init__(**data)

    @property
    def input_tokens(self) -> int | None:
        return self.prompt_tokens

    @property
    def output_tokens(self) -> int | None:
        return self.completion_tokens


class ModelRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: str
    messages: list[Message]
    system: str | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | None = None
    response_format: dict[str, str] | None = None
    temperature: float | None = None
    max_tokens: int | None = None


class ModelResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    content: str | None = None
    model: str = "default"
    provider: str = "default"
    usage: ModelUsage | None = None
    attempts: int = 1
    tool_calls: list[ToolCall] = Field(default_factory=list)


class ProviderHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    ok: bool
    detail: str
    latency_ms: float | None = None


class ModelProvider(ABC):
    @abstractmethod
    async def generate(self, request: ModelRequest) -> ModelResponse:
        pass

    @abstractmethod
    def stream(self, request: ModelRequest) -> AsyncIterator[str]:
        pass

    @abstractmethod
    async def health(self) -> ProviderHealth:
        pass

    @abstractmethod
    async def aclose(self) -> None:
        pass
