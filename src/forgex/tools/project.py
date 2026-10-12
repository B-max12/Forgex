"""project_info tool — what an agent first sees about the repository."""

from __future__ import annotations

from forgex.project import detect_project
from forgex.sandbox.permissions import Permission
from forgex.tools.base import SimpleTool, Tool, ToolCall, ToolContext, ToolResult
from forgex.tools.git import current_branch, is_dirty


async def _project_info(call: ToolCall, ctx: ToolContext) -> ToolResult:
    detection = detect_project(ctx.workspace)
    branch = current_branch(ctx.workspace)
    dirty = is_dirty(ctx.workspace) if branch else None
    git_state = f"{branch} ({'dirty' if dirty else 'clean'})" if branch else "not a git repository"
    output = "\n".join(
        [
            f"Project:    {detection.summary()}",
            f"Workspace:  {ctx.workspace}",
            f"Git:        {git_state}",
        ]
    )
    return ToolResult(
        ok=True,
        output=output,
        data={**detection.as_dict(), "git": {"branch": branch, "dirty": dirty}},
    )


def create_tools() -> list[Tool]:
    return [
        SimpleTool(
            name="project_info",
            handler=_project_info,
            permissions={Permission.READ},
            description="Overview of the project: languages, frameworks, package managers, git state.",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
        ),
    ]
