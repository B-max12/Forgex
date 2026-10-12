"""Workspace-safe path resolution.

Every filesystem operation performed by FORGEX tools must obtain its
target path through :func:`resolve_in_workspace`. This is a core security
boundary: agents must never touch paths outside the authorized workspace.
"""

from __future__ import annotations

from pathlib import Path

from forgex.schemas.error import PathViolationError

FORGEX_DIR_NAME = ".forgex"

__all__ = ["PathViolationError", "find_project_root", "resolve_in_workspace"]


def resolve_in_workspace(workspace: str | Path, target: str | Path) -> Path:
    """Resolve *target* inside *workspace* and refuse any escape.

    Rules enforced:
      * Relative targets are joined to the workspace.
      * Absolute targets must already be inside the workspace.
      * ``..`` traversal that would leave the workspace is rejected.
      * Symlinks are resolved; links pointing outside the workspace are
        rejected (containment is checked on the final real path).
      * The workspace root itself is allowed (needed for listing).
    """
    workspace = Path(workspace).resolve()
    candidate = Path(target)

    resolved = candidate.resolve() if candidate.is_absolute() else (workspace / candidate).resolve()

    if resolved != workspace and workspace not in resolved.parents:
        msg = f"path escapes workspace: {target!r} -> {resolved}"
        raise PathViolationError(msg)

    return resolved


def find_project_root(start: str | Path | None = None) -> Path | None:
    """Walk upward from *start* (default: cwd) looking for a .forgex directory."""
    current = (Path(start) if start else Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / FORGEX_DIR_NAME).is_dir():
            return candidate
    return None
