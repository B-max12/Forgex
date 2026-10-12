"""`forgex review` — run the Expert Coder over recent changes (spec section 10)."""

from __future__ import annotations

import asyncio
from typing import Annotated, Optional

import typer
from rich.markup import escape

from forgex.agents.expert_coder import review_work
from forgex.cli.ui import JsonFlag, Output, PlainFlag, make_approval, ui_from
from forgex.config import load_config
from forgex.orchestration.stores import open_stores
from forgex.schemas.error import ProjectError
from forgex.utils.paths import find_project_root


def review_command(
    ctx: typer.Context,
    task_id: Annotated[Optional[str], typer.Argument(help="Review this task's changes (default: current uncommitted changes).")] = None,
    base: Annotated[Optional[str], typer.Option("--base", help="Explicit base commit for the review diff.")] = None,
    json_out: JsonFlag = False,
    plain: PlainFlag = False,
) -> None:
    """Expert review of recent changes: fix, simplify, harden — minimally."""
    ui = ui_from(ctx, json_out=json_out, plain=plain)
    root = find_project_root()
    if root is None:
        raise ProjectError("Not inside a FORGEX project — run `forgex init` first.")

    config = load_config(root)
    with open_stores(root) as stores:
        result = asyncio.run(
            review_work(
                stores=stores,
                config=config,
                task_id=task_id,
                base_commit=base,
                approval=make_approval(ui),
            )
        )

    if result is None:
        ui.data({"reviewed": False})
        ui.ok("Nothing to review — no changes detected.")
        return

    ui.data({
        "reviewed": True,
        "status": result.status,
        "summary": result.summary,
        "improvements": result.improvements,
        "issues_found": result.issues_found,
        "unfixed_issues": result.unfixed_issues,
        "changed_files": result.changed_files,
    })

    if result.status != "completed":
        ui.error(f"Review failed: {result.summary}")
        raise typer.Exit(code=1)

    if result.changed_files:
        ui.ok(f"Review complete — {len(result.improvements)} improvement(s), {len(result.changed_files)} file(s) changed")
    else:
        ui.ok(f"Review complete — no changes needed ({result.summary})")

    if ui.mode in (Output.RICH, Output.PLAIN):
        for item in result.improvements:
            ui.text(f"  • {escape(item)}")
        for path in result.changed_files:
            ui.text(f"  changed: {escape(path)}")
        if result.unfixed_issues:
            ui.text("  Unfixed issues:")
            for issue in result.unfixed_issues:
                ui.text(f"    - {escape(issue)}")
