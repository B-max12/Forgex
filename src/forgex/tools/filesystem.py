"""Filesystem tools (spec sections 18, 46, 75).

Every agent filesystem operation routes through resolve_in_workspace().
Protected paths (.forgex/, .git/, workspace root) and secret files (.env*, keys)
are guarded.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path

from forgex.sandbox.permissions import Permission
from forgex.schemas.error import PathViolationError, ToolError
from forgex.tools.base import SimpleTool, Tool, ToolCall, ToolContext, ToolResult
from forgex.utils.paths import resolve_in_workspace
from forgex.utils.redact import redact_patterns

IGNORED_DIRS: set[str] = {
    ".git",
    ".forgex",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
}

_SECRET_FILE_PATTERNS = [
    ".env*",
    "*.pem",
    "id_rsa*",
    "id_ed25519*",
    ".npmrc",
    "*.key",
    "*credentials*",
    "*secret*",
]

MAX_READ_BYTES = 200_000
MAX_READ_LINES = 2000
MAX_LIST_COUNT = 500


def is_secret_file(name: str) -> bool:
    lower = name.lower()
    return any(fnmatch.fnmatch(lower, pat) for pat in _SECRET_FILE_PATTERNS)


def _resolve_path(ctx: ToolContext, raw: str) -> Path:
    try:
        return resolve_in_workspace(ctx.workspace, raw)
    except PathViolationError as exc:
        raise ToolError(str(exc)) from exc
    except (ValueError, OSError) as exc:
        raise ToolError(f"invalid path: {exc}") from exc


def _rel(ctx: ToolContext, path: Path) -> str:
    try:
        return str(path.relative_to(ctx.workspace))
    except ValueError:
        return str(path)


def _assert_mutable(ctx: ToolContext, path: Path, raw: str) -> None:
    if path == ctx.workspace.resolve():
        raise ToolError("refusing to modify the workspace root")

    lexical = Path(raw)
    if not lexical.is_absolute():
        lexical = ctx.workspace / lexical
    if lexical.is_symlink():
        raise ToolError(f"refusing to modify through a symlink: {raw}")

    rel = Path(_rel(ctx, path))
    top = rel.parts[0] if rel.parts else ""
    if top in {".forgex", ".git"}:
        raise ToolError("refusing to modify protected path (.forgex/ and .git/ are system-owned)")


async def _list_files(call: ToolCall, ctx: ToolContext) -> ToolResult:
    sub = str(call.arguments.get("path", ".") or ".")
    pattern = call.arguments.get("pattern")
    target = _resolve_path(ctx, sub)

    if not target.is_dir():
        return ToolResult(ok=False, error=f"Not a directory: {sub}")

    entries: list[str] = []
    truncated = False

    for item in sorted(target.rglob("*")):
        # Skip ignored directories
        rel = item.relative_to(ctx.workspace)
        parts = rel.parts
        if any(p in IGNORED_DIRS for p in parts):
            continue
        if item.is_file():
            if pattern and not fnmatch.fnmatch(item.name, pattern):
                continue
            entries.append(rel.as_posix())
            if len(entries) >= MAX_LIST_COUNT:
                truncated = True
                break

    lines = list(entries)
    if truncated:
        lines.append(f"... [truncated at {MAX_LIST_COUNT} entries]")

    return ToolResult(
        ok=True,
        output="\n".join(lines) or "(empty)",
        data={"count": len(entries), "truncated": truncated},
    )


async def _read_file(call: ToolCall, ctx: ToolContext) -> ToolResult:
    path_arg = call.arguments.get("path")
    if not path_arg:
        return ToolResult(ok=False, error="missing required argument: path")

    target = _resolve_path(ctx, str(path_arg))

    if is_secret_file(target.name):
        return ToolResult(ok=False, error=f"refusing to read secret-bearing file: {target.name}")

    if not target.is_file():
        return ToolResult(ok=False, error=f"file not found: {path_arg}")

    try:
        raw_bytes = target.read_bytes()
    except OSError as exc:
        return ToolResult(ok=False, error=f"failed to read file: {exc}")

    # Redact patterns before processing
    text = redact_patterns(raw_bytes[:MAX_READ_BYTES].decode("utf-8", errors="replace"))
    lines = text.splitlines()

    truncated = False
    if len(raw_bytes) > MAX_READ_BYTES or len(lines) > MAX_READ_LINES:
        truncated = True
        lines = lines[:MAX_READ_LINES]
        lines.append("... [file truncated]")

    return ToolResult(
        ok=True,
        output="\n".join(lines),
        data={"path": _rel(ctx, target), "lines": len(lines), "truncated": truncated},
    )


async def _write_file(call: ToolCall, ctx: ToolContext) -> ToolResult:
    path_arg = call.arguments.get("path")
    content = call.arguments.get("content")
    if path_arg is None or content is None:
        return ToolResult(ok=False, error="missing path or content argument")

    target = _resolve_path(ctx, str(path_arg))
    _assert_mutable(ctx, target, str(path_arg))

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(content), encoding="utf-8")
        return ToolResult(ok=True, output=f"wrote {len(content)} characters to {path_arg}")
    except OSError as exc:
        return ToolResult(ok=False, error=f"failed to write file: {exc}")


async def _create_file(call: ToolCall, ctx: ToolContext) -> ToolResult:
    path_arg = call.arguments.get("path")
    content = call.arguments.get("content", "")
    if path_arg is None:
        return ToolResult(ok=False, error="missing path argument")

    target = _resolve_path(ctx, str(path_arg))
    _assert_mutable(ctx, target, str(path_arg))

    if target.exists():
        return ToolResult(ok=False, error=f"file already exists: {path_arg}")

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(content), encoding="utf-8")
        return ToolResult(ok=True, output=f"created file {path_arg}")
    except OSError as exc:
        return ToolResult(ok=False, error=f"failed to create file: {exc}")


async def _delete_file(call: ToolCall, ctx: ToolContext) -> ToolResult:
    path_arg = call.arguments.get("path")
    if not path_arg:
        return ToolResult(ok=False, error="missing path argument")

    target = _resolve_path(ctx, str(path_arg))
    _assert_mutable(ctx, target, str(path_arg))

    if not target.exists():
        return ToolResult(ok=False, error=f"file not found: {path_arg}")
    if target.is_dir():
        return ToolResult(ok=False, error=f"refusing to delete directory: {path_arg}")

    try:
        target.unlink()
        return ToolResult(ok=True, output=f"deleted file {path_arg}")
    except OSError as exc:
        return ToolResult(ok=False, error=f"failed to delete file: {exc}")


async def _move_file(call: ToolCall, ctx: ToolContext) -> ToolResult:
    src_arg = call.arguments.get("source")
    dst_arg = call.arguments.get("destination")
    if not src_arg or not dst_arg:
        return ToolResult(ok=False, error="missing source or destination argument")

    src = _resolve_path(ctx, str(src_arg))
    dst = _resolve_path(ctx, str(dst_arg))
    _assert_mutable(ctx, src, str(src_arg))
    _assert_mutable(ctx, dst, str(dst_arg))

    if not src.exists():
        return ToolResult(ok=False, error=f"source file not found: {src_arg}")

    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
        return ToolResult(ok=True, output=f"moved {src_arg} -> {dst_arg}")
    except OSError as exc:
        return ToolResult(ok=False, error=f"failed to move file: {exc}")


def create_tools() -> list[Tool]:
    path_prop = {"type": "string", "description": "Workspace-relative file path"}
    return [
        SimpleTool(
            name="list_files",
            handler=_list_files,
            permissions={Permission.READ},
            description="List files in the workspace (ignores git/cache/build noise).",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Subdirectory (default: workspace root)"},
                    "pattern": {"type": "string", "description": "Optional glob filter on file names"},
                },
                "additionalProperties": False,
            },
        ),
        SimpleTool(
            name="read_file",
            handler=_read_file,
            permissions={Permission.READ},
            description="Read a file (capped at 200KB / 2000 lines; secret files like .env are refused).",
            parameters={
                "type": "object",
                "properties": {"path": path_prop},
                "required": ["path"],
                "additionalProperties": False,
            },
        ),
        SimpleTool(
            name="write_file",
            handler=_write_file,
            permissions={Permission.WRITE},
            description="Write a file (overwrites; creates parent directories).",
            parameters={
                "type": "object",
                "properties": {
                    "path": path_prop,
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
        ),
        SimpleTool(
            name="create_file",
            handler=_create_file,
            permissions={Permission.WRITE},
            description="Create a new file; fails if it already exists.",
            parameters={
                "type": "object",
                "properties": {
                    "path": path_prop,
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
        ),
        SimpleTool(
            name="delete_file",
            handler=_delete_file,
            permissions={Permission.DELETE},
            description="Delete a single file (never directories).",
            parameters={
                "type": "object",
                "properties": {"path": path_prop},
                "required": ["path"],
                "additionalProperties": False,
            },
        ),
        SimpleTool(
            name="move_file",
            handler=_move_file,
            permissions={Permission.WRITE},
            description="Move or rename a file inside the workspace.",
            parameters={
                "type": "object",
                "properties": {
                    "source": path_prop,
                    "destination": path_prop,
                },
                "required": ["source", "destination"],
                "additionalProperties": False,
            },
        ),
    ]
