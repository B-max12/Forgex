"""run_tests tool + test-command detection (spec section 10)."""

from __future__ import annotations

import json
import shlex
from pathlib import Path

from forgex.project import detect_project
from forgex.sandbox.permissions import Permission
from forgex.tools.base import SimpleTool, Tool, ToolCall, ToolContext, ToolResult


def detect_test_command(root: Path) -> list[str] | None:
    detection = detect_project(root)
    langs = detection.languages
    frameworks = detection.test_frameworks

    if "Python" in langs:
        if "Pytest" in frameworks:
            return ["python", "-m", "pytest", "-q"]
        if "unittest" in frameworks:
            return ["python", "-m", "unittest", "discover", "-s", "."]
        return None

    if "JavaScript" in langs or "TypeScript" in langs:
        pkg = root / "package.json"
        if pkg.is_file():
            try:
                scripts = json.loads(pkg.read_text(encoding="utf-8")).get("scripts") or {}
                if scripts.get("test"):
                    return ["npm", "test"]
            except (OSError, json.JSONDecodeError):
                return None
        return None

    if "Rust" in langs:
        return ["cargo", "test"]

    if "Go" in langs:
        return ["go", "test", "./..."]

    return None


async def _run_tests(call: ToolCall, ctx: ToolContext) -> ToolResult:
    command = detect_test_command(ctx.workspace)
    if command is None:
        return ToolResult(
            ok=False,
            error="No test command detected for this project (expected pytest / npm test / cargo test / go test).",
        )

    extra = call.arguments.get("extra_args") or []
    full_cmd = list(command) + [str(a) for a in extra]

    result = await ctx.executor.run(full_cmd, cwd=".")
    status = "killed (timeout)" if result.timed_out else f"exit code {result.exit_code}"
    output = "\n".join(
        [
            f"$ {shlex.join(result.argv)}",
            status,
            "--- stdout ---",
            result.stdout or "(empty)",
            "--- stderr ---",
            result.stderr or "(empty)",
        ]
    )
    return ToolResult(
        ok=(result.exit_code == 0 and not result.timed_out),
        output=output,
        data={
            "command": result.argv,
            "exit_code": result.exit_code,
            "timed_out": result.timed_out,
            "duration_ms": round(result.duration_ms, 1),
        },
    )


def create_tools() -> list[Tool]:
    return [
        SimpleTool(
            name="run_tests",
            handler=_run_tests,
            permissions={Permission.TEST},
            description="Run the project's test suite (auto-detected: pytest, npm test, cargo test, go test).",
            parameters={
                "type": "object",
                "properties": {
                    "extra_args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Extra arguments appended to the test command",
                    }
                },
                "additionalProperties": False,
            },
        ),
    ]
