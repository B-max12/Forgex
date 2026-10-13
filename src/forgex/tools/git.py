"""Git primitives and agent tools (spec section 21).

The checkpoint system: `git_checkpoint` commits all current work with a
'forgex:' message (identity falls back to FORGEX <forgex@localhost> when
the user has none configured). Non-destructive: commits preserve work.
Checkpoint metadata + `forgex checkpoint/rollback` CLI arrive in Phase 6.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("forgex.git")

MAX_DIFF_BYTES = 50_000
_EXCLUDE_FORGEX = [":(exclude).forgex"]


@dataclass
class GitResult:
    rc: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.rc == 0


def _git(args: list[str], cwd: Path) -> GitResult | None:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        return GitResult(rc=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)
    except (OSError, subprocess.TimeoutExpired):
        return None


def has_git_repo(root: Path) -> bool:
    return (root / ".git").exists()


def current_branch(root: Path) -> str | None:
    r = _git(["rev-parse", "--abbrev-ref", "HEAD"], root)
    return r.stdout.strip() if r and r.ok else None


def is_dirty(root: Path) -> bool | None:
    r = _git(["status", "--porcelain"], root)
    if r is None or not r.ok:
        return None
    lines = [ln for ln in r.stdout.splitlines() if ".forgex" not in ln]
    return bool(lines)


def git_status(root: Path) -> str:
    if not has_git_repo(root):
        return "not a git repository"
    r = _git(["status", "--short"], root)
    return r.stdout.strip() if r and r.ok else "git status failed"


def git_diff(root: Path, *, staged: bool = False) -> str:
    if not has_git_repo(root):
        return "not a git repository"
    args = ["diff"] + (["--cached"] if staged else []) + ["--", "."] + _EXCLUDE_FORGEX
    r = _git(args, root)
    if r is None or not r.ok:
        return "git diff failed"
    out = r.stdout
    if len(out) > MAX_DIFF_BYTES:
        out = out[:MAX_DIFF_BYTES] + "\n... [diff truncated]"
    return out


def git_diff_range(root: Path, base_commit: str) -> str:
    if not has_git_repo(root):
        return "not a git repository"
    args = ["diff", base_commit, "HEAD", "--", "."] + _EXCLUDE_FORGEX
    r = _git(args, root)
    if r is None or not r.ok:
        return "(no diff available)"
    out = r.stdout
    if len(out) > MAX_DIFF_BYTES:
        out = out[:MAX_DIFF_BYTES] + "\n... [diff truncated]"
    return out


def git_diff_stat(root: Path, target_commit: str) -> str:
    r = _git(["diff", "--stat", "HEAD", target_commit], root)
    return r.stdout.strip() if r and r.ok else "(no diff preview available)"


def git_changed_files(root: Path, base_commit: str | None = None) -> list[str]:
    if not has_git_repo(root):
        return []
    if base_commit:
        r = _git(["diff", "--name-only", base_commit, "HEAD", "--", "."] + _EXCLUDE_FORGEX, root)
        if r is None or not r.ok:
            return []
        return [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]

    r = _git(["status", "--porcelain"], root)
    if r is None or not r.ok:
        return []
    files: list[str] = []
    for line in r.stdout.splitlines():
        if not line.strip():
            continue
        # Format: XY filename or XY orig -> new
        name = line[3:].strip()
        if " -> " in name:
            name = name.split(" -> ")[1].strip()
        if name.startswith(".forgex/") or name == ".forgex":
            continue
        files.append(name)
    return files


def git_log(root: Path, limit: int = 10) -> str:
    if not has_git_repo(root):
        return "not a git repository"
    r = _git(["log", f"-n{limit}", "--format=%H %s"], root)
    return r.stdout.strip() if r and r.ok else "git log failed"


def _has_user_identity(root: Path) -> bool:
    name = _git(["config", "user.name"], root)
    email = _git(["config", "user.email"], root)
    return bool(name and name.ok and name.stdout.strip() and email and email.ok and email.stdout.strip())


def _ensure_git_exclude_forgex(root: Path) -> None:
    exclude_file = root / ".git" / "info" / "exclude"
    if exclude_file.is_file():
        try:
            content = exclude_file.read_text(encoding="utf-8")
            if ".forgex" not in content:
                exclude_file.write_text(content.rstrip() + "\n.forgex\n.forgex/**\n", encoding="utf-8")
        except Exception:
            pass


def git_checkpoint(root: Path, label: str) -> str | None:
    if not has_git_repo(root):
        return None

    _ensure_git_exclude_forgex(root)

    # Check current HEAD commit before committing
    head_before = _git(["rev-parse", "HEAD"], root)

    _git(["add", "-A", "--", ".", ":(exclude).forgex"], root)
    commit_args = ["commit", "-m", f"forgex: {label}", "--allow-empty-message"]
    if not _has_user_identity(root):
        commit_args = [
            "-c", "user.name=FORGEX",
            "-c", "user.email=forgex@localhost",
            *commit_args,
        ]
    _git(commit_args, root)
    head_after = _git(["rev-parse", "HEAD"], root)

    if head_after and head_after.ok:
        return head_after.stdout.strip()
    return head_before.stdout.strip() if head_before and head_before.ok else None


def git_reset_hard(root: Path, commit: str) -> bool:
    r = _git(["reset", "--hard", commit], root)
    return bool(r and r.ok)


# Agent tools factory
def create_tools() -> list[Any]:
    from forgex.sandbox.permissions import Permission
    from forgex.tools.base import SimpleTool, ToolCall, ToolContext, ToolResult

    async def _tool_status(call: ToolCall, ctx: ToolContext) -> ToolResult:
        st = git_status(ctx.workspace)
        return ToolResult(ok=True, output=st)

    async def _tool_diff(call: ToolCall, ctx: ToolContext) -> ToolResult:
        staged = bool(call.arguments.get("staged", False))
        diff = git_diff(ctx.workspace, staged=staged)
        return ToolResult(ok=True, output=diff)

    async def _tool_log(call: ToolCall, ctx: ToolContext) -> ToolResult:
        limit = int(call.arguments.get("limit", 10))
        lg = git_log(ctx.workspace, limit=limit)
        return ToolResult(ok=True, output=lg)

    async def _tool_checkpoint(call: ToolCall, ctx: ToolContext) -> ToolResult:
        label = str(call.arguments.get("label", "manual"))
        c = git_checkpoint(ctx.workspace, label)
        if c is None:
            return ToolResult(ok=False, error="git checkpoint failed (no git repo or commit error)")
        return ToolResult(ok=True, output=f"checkpoint created: {c[:8]} ({label})", data={"commit": c})

    return [
        SimpleTool(
            name="git_status",
            handler=_tool_status,
            permissions={Permission.GIT},
            description="Show the working tree status.",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
        ),
        SimpleTool(
            name="git_diff",
            handler=_tool_diff,
            permissions={Permission.GIT},
            description="Show changes between commits, commit and working tree, etc.",
            parameters={"type": "object", "properties": {"staged": {"type": "boolean"}}, "additionalProperties": False},
        ),
        SimpleTool(
            name="git_log",
            handler=_tool_log,
            permissions={Permission.GIT},
            description="Show recent commit logs.",
            parameters={"type": "object", "properties": {"limit": {"type": "integer"}}, "additionalProperties": False},
        ),
        SimpleTool(
            name="git_checkpoint",
            handler=_tool_checkpoint,
            permissions={Permission.GIT},
            description="Create a Git checkpoint of current workspace changes.",
            parameters={"type": "object", "properties": {"label": {"type": "string"}}, "required": ["label"], "additionalProperties": False},
        ),
    ]
