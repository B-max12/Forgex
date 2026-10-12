"""Search tools (spec sections 3, 18, 46): ripgrep when available, pure-Python fallback."""

from __future__ import annotations

import asyncio
import fnmatch
import os
import re
import shutil
from pathlib import Path
from typing import Any

from forgex.sandbox.permissions import Permission
from forgex.schemas.error import ToolError
from forgex.tools.base import SimpleTool, Tool, ToolCall, ToolContext, ToolResult
from forgex.tools.filesystem import IGNORED_DIRS, is_secret_file
from forgex.utils.redact import redact_patterns

MAX_MATCHES = 200
MAX_SCAN_FILES = 5_000
TEXT_SUFFIX_SKIP = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip",
    ".gz", ".tar", ".bin", ".exe", ".dll", ".so", ".dylib", ".db",
    ".sqlite", ".sqlite3", ".woff", ".woff2", ".ttf", ".class",
}


def _rg_available() -> bool:
    return shutil.which("rg") is not None


async def _rg_search(
    root: Path, query: str, glob: str | None, *, regex: bool, limit: int
) -> tuple[list[str], bool]:
    argv = [
        "rg",
        "--line-number",
        "--no-heading",
        "--color",
        "never",
        "--smart-case" if regex else "--fixed-strings",
    ]
    for ignored in IGNORED_DIRS:
        argv.extend(["--glob", f"!{ignored}/**"])
    argv.extend(["--glob", "!.env*"])
    if glob:
        argv.extend(["--glob", glob])
    argv.extend(["--", query, str(root)])

    try:
        proc = await asyncio.create_subprocess_exec(
            *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
    except (OSError, asyncio.TimeoutError):
        return [], False

    lines = stdout.decode("utf-8", errors="replace").splitlines()
    truncated = len(lines) > limit
    cleaned: list[str] = []
    root_str = str(root.resolve())
    for line in lines[:limit]:
        if line.startswith(root_str):
            line = line[len(root_str) :].lstrip("/\\")
        cleaned.append(line)

    return cleaned, truncated


def _python_search(
    root: Path, query: str, glob: str | None, *, regex: bool, limit: int
) -> tuple[list[str], bool]:
    pattern = re.compile(query, re.IGNORECASE) if regex else None
    matches: list[str] = []
    truncated = False
    scanned = 0

    for path in sorted(root.rglob("*")):
        if scanned >= MAX_SCAN_FILES:
            truncated = True
            break
        try:
            rel = path.relative_to(root)
        except ValueError:
            continue
        if any(p in IGNORED_DIRS for p in rel.parts):
            continue
        if is_secret_file(path.name):
            continue
        if not path.is_file():
            continue
        if path.suffix.lower() in TEXT_SUFFIX_SKIP:
            continue
        if glob and not fnmatch.fnmatch(path.name, glob):
            continue

        scanned += 1
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        for idx, line in enumerate(content.splitlines(), start=1):
            matched = bool(pattern.search(line)) if pattern else (query in line)
            if matched:
                matches.append(f"{rel.as_posix()}:{idx}: {line.strip()[:200]}")
                if len(matches) >= limit:
                    truncated = True
                    return matches, truncated

    return matches, truncated


async def _search_code(call: ToolCall, ctx: ToolContext) -> ToolResult:
    query = call.arguments.get("query")
    if not query:
        return ToolResult(ok=False, error="missing required argument: query")

    regex = bool(call.arguments.get("regex", False))
    glob = call.arguments.get("glob")
    limit = int(call.arguments.get("limit", MAX_MATCHES))

    if _rg_available():
        engine = "ripgrep"
        matches, truncated = await _rg_search(ctx.workspace, str(query), glob, regex=regex, limit=limit)
    else:
        engine = "python"
        matches, truncated = _python_search(ctx.workspace, str(query), glob, regex=regex, limit=limit)

    redacted_matches = [redact_patterns(m) for m in matches]
    output = "\n".join(redacted_matches) if redacted_matches else "(no matches)"

    return ToolResult(
        ok=True,
        output=output,
        data={"matches": len(matches), "truncated": truncated, "engine": engine},
    )


async def _search_files(call: ToolCall, ctx: ToolContext) -> ToolResult:
    pattern = call.arguments.get("pattern")
    if not pattern:
        return ToolResult(ok=False, error="missing required argument: pattern")

    sub = str(call.arguments.get("path", ".") or ".")
    try:
        from forgex.utils.paths import resolve_in_workspace
        target = resolve_in_workspace(ctx.workspace, sub)
    except Exception as exc:
        return ToolResult(ok=False, error=str(exc))

    matches: list[str] = []
    truncated = False

    for path in sorted(target.rglob("*")):
        try:
            rel = path.relative_to(ctx.workspace)
        except ValueError:
            continue
        if any(p in IGNORED_DIRS for p in rel.parts):
            continue
        if is_secret_file(path.name):
            continue
        if fnmatch.fnmatch(path.name, str(pattern)):
            matches.append(rel.as_posix())
            if len(matches) >= MAX_MATCHES:
                truncated = True
                break

    output = "\n".join(matches) if matches else "(no files matched)"
    return ToolResult(ok=True, output=output, data={"count": len(matches), "truncated": truncated})


def create_tools() -> list[Tool]:
    return [
        SimpleTool(
            name="search_code",
            handler=_search_code,
            permissions={Permission.READ},
            description="Search for text or regex in workspace code files.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "String or regex pattern to search for"},
                    "regex": {"type": "boolean", "description": "Whether query is a regex"},
                    "glob": {"type": "string", "description": "Optional file glob filter, e.g. *.py"},
                    "limit": {"type": "integer", "description": "Maximum match count"},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        ),
        SimpleTool(
            name="search_files",
            handler=_search_files,
            permissions={Permission.READ},
            description="Find files in the workspace matching a name glob pattern.",
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Filename pattern to match, e.g. *test*.py"},
                    "path": {"type": "string", "description": "Subdirectory to search inside"},
                },
                "required": ["pattern"],
                "additionalProperties": False,
            },
        ),
    ]
