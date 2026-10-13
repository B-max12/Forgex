"""`forgex rollback` — restore workspace to a checkpoint (spec sections 21, 33)."""

from __future__ import annotations

import sys
from typing import Annotated

import typer
from rich.prompt import Confirm

from forgex.cli.ui import JsonFlag, Output, PlainFlag, ui_from
from forgex.orchestration.checkpoints import get_checkpoint, latest_checkpoint, rollback_to
from forgex.orchestration.stores import open_stores
from forgex.schemas.error import ProjectError
from forgex.tools.git import git_diff_stat
from forgex.utils.paths import find_project_root


def rollback_command(
    ctx: typer.Context,
    checkpoint_id: Annotated[str | None, typer.Argument(help="Checkpoint id (default: latest)")] = None,
    last: Annotated[bool, typer.Option("--last", help="Rollback to latest checkpoint.")] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation prompt.")] = False,
    json_out: JsonFlag = False,
    plain: PlainFlag = False,
) -> None:
    """Roll the workspace back to a checkpoint (reversible)."""
    ui = ui_from(ctx, json_out=json_out, plain=plain)
    root = find_project_root()
    if root is None:
        raise ProjectError("Not inside a FORGEX project — run `forgex init` first.")

    with open_stores(root) as stores:
        if checkpoint_id and not last:
            record = get_checkpoint(checkpoint_id, stores=stores)
            if record is None:
                raise ProjectError(f"Unknown checkpoint: {checkpoint_id}")
        else:
            record = latest_checkpoint(stores=stores)
            if record is None:
                raise ProjectError("No checkpoints recorded yet — run `forgex checkpoint`.")

        ui.text(f"Rolling back to {record.id} — {record.label} (commit {record.git_commit[:8] if record.git_commit else '?'})")
        preview = git_diff_stat(root, record.git_commit) if record.git_commit else ""
        if preview and preview != "(no diff preview available)":
            ui.text(f"Changes to be reverted:\n{preview}")

        if not yes:
            if not sys.stdin.isatty() or ui.mode is not Output.RICH:
                ui.warn("Refusing to rollback non-interactively without --yes.")
                raise typer.Exit(code=1)
            if not Confirm.ask("Proceed with rollback?", default=False):
                ui.warn("Aborted — nothing changed.")
                raise typer.Exit(code=1)

        safety = rollback_to(record, stores=stores)

    ui.data({
        "rolled_back_to": record.id,
        "commit": record.git_commit,
        "safety_checkpoint": safety.id if safety else None,
    })
    ui.ok(f"Rolled back to {record.id} ({record.label})")
    if safety:
        ui.text(f"Safety checkpoint: {safety.id} — undo this rollback with `forgex rollback {safety.id}`")
