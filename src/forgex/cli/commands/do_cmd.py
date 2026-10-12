"""`forgex do` — end-to-end autonomous execution pipeline."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer

from forgex.cli.progress import render_pipeline_header, render_runtime_summary
from forgex.cli.runtime import AutonomousRuntime
from forgex.cli.ui import JsonFlag, Output, PlainFlag, ui_from


def do_command(
    ctx: typer.Context,
    request: Annotated[list[str], typer.Argument(help="What to build or modify")],
    resume: Annotated[bool, typer.Option("--resume", "-r", help="Resume interrupted build.")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show execution preview without making changes.")] = False,
    json_out: JsonFlag = False,
    plain: PlainFlag = False,
) -> None:
    """Run full autonomous pipeline: auto-init → plan → build → verify → repair → checkpoint."""
    req_text = " ".join(request).strip()
    if not req_text:
        typer.echo("Error: Please describe what to build or modify.")
        raise typer.Exit(code=2)

    ui = ui_from(ctx, json_out=json_out, plain=plain)
    if ui.mode is Output.RICH and not dry_run:
        render_pipeline_header(req_text, console=ui.console)

    runtime = AutonomousRuntime(ui=ui)
    result = asyncio.run(runtime.execute(request=req_text, dry_run=dry_run, resume=resume))

    if json_out or (ctx.obj and ctx.obj.get("json")):
        ui.data({
            "status": result.status,
            "request": result.request,
            "tasks_total": result.tasks_total,
            "tasks_completed": result.tasks_completed,
            "changed_files": result.changed_files,
            "checkpoint": result.checkpoint_id,
            "phases": result.phases_completed,
            "duration": result.duration_seconds,
        })
    else:
        render_runtime_summary(result, console=ui.console)

    raise typer.Exit(code=0 if result.is_success else 1)
