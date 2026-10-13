"""`forgex checkpoint` — create a Git checkpoint of current state (spec section 21)."""

from __future__ import annotations

from typing import Annotated

import typer

from forgex.cli.ui import JsonFlag, PlainFlag, ui_from
from forgex.orchestration.checkpoints import create_checkpoint
from forgex.orchestration.stores import open_stores
from forgex.schemas.error import ProjectError
from forgex.tools.git import has_git_repo
from forgex.utils.paths import find_project_root


def checkpoint_command(
    ctx: typer.Context,
    label: Annotated[str | None, typer.Argument(help="Checkpoint label")] = None,
    json_out: JsonFlag = False,
    plain: PlainFlag = False,
) -> None:
    """Commit all current work as a FORGEX checkpoint."""
    ui = ui_from(ctx, json_out=json_out, plain=plain)
    root = find_project_root()
    if root is None:
        raise ProjectError("Not inside a FORGEX project — run `forgex init` first.")

    if not has_git_repo(root):
        ui.warn("No git repository detected — checkpointing requires git. Run 'git init'.")
        raise typer.Exit(code=0)

    with open_stores(root) as stores:
        record = create_checkpoint(label or "manual", stores=stores)

    if record is None:
        ui.error("Checkpoint failed (git error — see git status).")
        raise typer.Exit(code=1)

    ui.data({"id": record.id, "label": record.label, "git_commit": record.git_commit})
    ui.ok(f"Checkpoint {record.id} — {record.git_commit[:8] if record.git_commit else '?'} ({record.label})")
