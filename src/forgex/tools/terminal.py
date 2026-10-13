"""run_command tool (spec section 19) — gated through policy → approval → executor."""

from __future__ import annotations

import shlex

from forgex.sandbox.permissions import Permission
from forgex.schemas.error import ToolError
from forgex.tools.base import SimpleTool, Tool, ToolCall, ToolContext, ToolResult


async def _run_command(call: ToolCall, ctx: ToolContext) -> ToolResult:
    command = call.arguments.get("command")
    if command is None:
        raise ToolError("missing required argument: command")

    cwd = str(call.arguments.get("cwd", ".") or ".")
    timeout = call.arguments.get("timeout")
    env = call.arguments.get("env")

    result = await ctx.executor.run(
        command,
        cwd=cwd,
        timeout=float(timeout) if timeout is not None else None,
        env=env,
    )

    head = f"$ {shlex.join(result.argv)}"
    status = "killed (timeout)" if result.timed_out else f"exit code {result.exit_code}"
    sections = [
        head,
        status,
        "--- stdout ---",
        result.stdout or "(empty)",
        "--- stderr ---",
        result.stderr or "(empty)",
    ]
    return ToolResult(
        ok=(result.exit_code == 0 and not result.timed_out),
        output="\n".join(sections),
        data={
            "command": result.argv,
            "exit_code": result.exit_code,
            "timed_out": result.timed_out,
            "duration_ms": round(result.duration_ms, 1),
            "truncated": result.truncated,
        },
    )


def create_tools() -> list[Tool]:
    return [
        SimpleTool(
            name="run_command",
            handler=_run_command,
            permissions={Permission.TERMINAL},
            description=(
                "Run a command in the project workspace. Prefer an argv array "
                "(['python', '-m', 'pytest']). Strings are parsed with shlex — NO shell "
                "features (no pipes, &&, or redirects). The child environment is sanitized."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "description": "Argv array (preferred) or shlex-parsable string.",
                        "oneOf": [{"type": "array", "items": {"type": "string"}}, {"type": "string"}],
                    },
                    "cwd": {"type": "string", "description": "Workspace-relative working directory"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds"},
                    "env": {
                        "type": "object",
                        "additionalProperties": {"type": "string"},
                        "description": "Extra environment variables (parent env is NOT inherited)",
                    },
                },
                "required": ["command"],
                "additionalProperties": False,
            },
        ),
    ]
