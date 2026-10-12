"""`forgex diff` — show the current Git diff (spec section 21)."""

from __future__ import annotations

from typing import Annotated

import typer

from forgex.cli.ui import JsonFlag, PlainFlag, ui_from
from forgex.schemas.error import ProjectError
from forgex.tools.git import git_diff, has_git_repo
from forgex.utils.paths import find_project_root


def diff_command(
    ctx: typer.Context,
    staged: Annotated[bool, typer.Option("--staged", help="Show staged changes.")] = False,
    json_out: JsonFlag = False,
    plain: PlainFlag = False,
) -> None:
    """Show the current Git diff."""
    ui = ui_from(ctx, json_out=json_out, plain=plain)
    root = find_project_root()
    if root is None:
        raise ProjectError("Not inside a FORGEX project — run `forgex init` first.")
    if not has_git_repo(root):
        ui.text("not a git repository")
        raise typer.Exit(code=0)

    diff = git_diff(root, staged=staged)
    ui.data({"staged": staged, "diff": diff})
    ui.text(diff or "(no changes)")
