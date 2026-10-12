"""Tool system (spec sections 10, 18, 19, 32)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from forgex.config.schema import ForgexConfig
from forgex.orchestration.events import EventRecorder
from forgex.sandbox.executor import build_executor
from forgex.sandbox.permissions import Permission
from forgex.tools import dependencies as _dependencies
from forgex.tools import filesystem as _filesystem
from forgex.tools import git as _git
from forgex.tools import project as _project
from forgex.tools import search as _search
from forgex.tools import terminal as _terminal
from forgex.tools import testing as _testing
from forgex.tools.base import (
    SimpleTool,
    Tool,
    ToolCall,
    ToolContext,
    ToolExecutor,
    ToolRegistry,
    ToolResult,
)

__all__ = [
    "Permission",
    "SimpleTool",
    "Tool",
    "ToolCall",
    "ToolContext",
    "ToolExecutor",
    "ToolRegistry",
    "ToolResult",
    "build_tool_registry",
    "create_context",
]


def build_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for module in (_filesystem, _search, _terminal, _git, _testing, _dependencies, _project):
        for tool in module.create_tools():
            registry.register(tool)
    return registry


def create_context(
    workspace: Path | None = None,
    config: ForgexConfig | None = None,
    *,
    events: EventRecorder | None = None,
    approval: Callable[[str], bool] | None = None,
    run_id: str | None = None,
    agent=None,
    **kwargs: Any,
) -> ToolContext:
    ws = Path(workspace or kwargs.get("workspace") or Path.cwd()).resolve()
    cfg = config or kwargs.get("config") or ForgexConfig()
    executor = build_executor(workspace=ws, config=cfg, approval=approval)
    return ToolContext(
        workspace=ws,
        config=cfg,
        executor=executor,
        events=events,
        approval=approval,
        run_id=run_id,
        agent=agent,
    )
