"""Tool framework (spec sections 10, 18, 32).

Tools are the ONLY way agents touch the system. Every call passes
through ToolExecutor, which enforces the per-agent permission matrix.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import json
from pydantic import BaseModel, Field, model_validator

from forgex.config.schema import ForgexConfig
from forgex.orchestration.events import EventRecorder
from forgex.sandbox.executor import CommandExecutor
from forgex.sandbox.permissions import Permission, PermissionSet
from forgex.schemas.error import ForgexError, PermissionDeniedError
from forgex.schemas.event import EventType

logger = logging.getLogger("forgex.tools")


class ToolCall(BaseModel):
    id: str = ""
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _parse_arguments(cls, data: Any) -> Any:
        if isinstance(data, dict):
            args = data.get("arguments")
            if isinstance(args, str):
                try:
                    data["arguments"] = json.loads(args) if args.strip() else {}
                except Exception:
                    data["arguments"] = {}
        return data


class ToolResult(BaseModel):
    ok: bool = True
    output: str = ""
    error: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    denied: bool = False


@dataclass
class ToolContext:
    workspace: Path
    config: ForgexConfig
    executor: CommandExecutor
    events: EventRecorder | None = None
    approval: Callable[[str], bool] | None = None
    run_id: str | None = None
    agent: AgentRole | None = None


class Tool(ABC):
    name: str
    description: str
    required_permissions: set[Permission]

    @abstractmethod
    def parameters_schema(self) -> dict[str, Any]:
        pass

    @abstractmethod
    async def execute(self, call: ToolCall, ctx: ToolContext) -> ToolResult:
        pass


ToolHandler = Callable[[ToolCall, ToolContext], Awaitable[ToolResult]]


class SimpleTool(Tool):
    def __init__(
        self,
        name: str,
        handler: ToolHandler,
        permissions: set[Permission],
        description: str,
        parameters: dict[str, Any],
    ) -> None:
        self.name = name
        self._handler = handler
        self.required_permissions = permissions
        self.description = description
        self._parameters = parameters

    def parameters_schema(self) -> dict[str, Any]:
        return self._parameters

    async def execute(self, call: ToolCall, ctx: ToolContext) -> ToolResult:
        return await self._handler(call, ctx)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def tools(self) -> list[Tool]:
        return list(self._tools.values())

    def schemas_for(self, permissions: PermissionSet) -> list[dict[str, Any]]:
        schemas: list[dict[str, Any]] = []
        for tool in self._tools.values():
            if permissions.permits(*tool.required_permissions):
                schemas.append(
                    {
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": tool.parameters_schema(),
                        },
                    }
                )
        return schemas


class ToolExecutor:
    def __init__(
        self,
        registry: ToolRegistry,
        permissions: PermissionSet,
        context: ToolContext,
    ) -> None:
        self._registry = registry
        self._permissions = permissions
        self._context = context

    @property
    def context(self) -> ToolContext:
        return self._context

    def schemas(self) -> list[dict[str, Any]]:
        return self._registry.schemas_for(self._permissions)

    async def execute(self, call: ToolCall) -> ToolResult:
        tool = self._registry.get(call.name)
        if tool is None:
            return ToolResult(ok=False, error=f"Unknown tool: '{call.name}'")

        if not self._permissions.permits(*tool.required_permissions):
            reason = self._permissions.deny_reason(*tool.required_permissions) or "denied"
            msg = f"Permission denied for tool '{call.name}': {reason}"
            if self._context.events is not None:
                self._context.events.record(
                    EventType.TOOL_STARTED,
                    {"tool": call.name, "arguments": call.arguments},
                    run_id=self._context.run_id,
                )
                self._context.events.record(
                    EventType.TOOL_COMPLETED,
                    {"tool": call.name, "ok": False, "denied": True, "error": msg},
                    run_id=self._context.run_id,
                )
            raise PermissionDeniedError(msg)

        if self._context.events is not None:
            self._context.events.record(
                EventType.TOOL_STARTED,
                {"tool": call.name, "arguments": call.arguments},
                run_id=self._context.run_id,
            )

        start = time.perf_counter()
        try:
            result = await tool.execute(call, self._context)
        except ForgexError as exc:
            result = ToolResult(ok=False, error=str(exc))
        except Exception as exc:  # noqa: BLE001
            result = ToolResult(ok=False, error=f"Tool execution failed: {exc}")

        duration = (time.perf_counter() - start) * 1000

        if self._context.events is not None:
            if result.ok and call.name in ("write_file", "create_file", "delete_file", "move_file"):
                target = call.arguments.get("path") or call.arguments.get("destination")
                self._context.events.record(
                    EventType.FILE_CHANGED,
                    {"tool": call.name, "path": target},
                    run_id=self._context.run_id,
                )
            self._context.events.record(
                EventType.TOOL_COMPLETED,
                {
                    "tool": call.name,
                    "ok": result.ok,
                    "error": result.error,
                    "duration_ms": round(duration, 1),
                },
                run_id=self._context.run_id,
            )

        return result
