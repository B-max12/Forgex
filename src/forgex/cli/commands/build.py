"""`forgex build` — full multi-agent build pipeline with repair loop (spec sections 12, 22, 57, 58)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer

from forgex.cli.build_views import _render_failure, _render_success, format_progress
from forgex.cli.ui import JsonFlag, Output, PlainFlag, make_approval, ui_from
from forgex.config import load_config
from forgex.orchestration.engine import BuildEngine, DryRunReport
from forgex.orchestration.stores import open_stores
from forgex.schemas.error import ProjectError
from forgex.utils.paths import find_project_root


def build_command(
    ctx: typer.Context,
    request: Annotated[str | None, typer.Argument(help="What should be built?")] = None,
    file: Annotated[Path | None, typer.Option("--file", "-f", help="Read user request from file.")] = None,
    resume: Annotated[bool, typer.Option("--resume", "-r", help="Resume interrupted build.")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show execution preview without making changes.")] = False,
    json_out: JsonFlag = False,
    plain: PlainFlag = False,
) -> None:
    """Full build: plan → build → review → verify → supervise → repair loop."""
    ui = ui_from(ctx, json_out=json_out, plain=plain)
    root = find_project_root()
    if root is None:
        raise ProjectError("Not inside a FORGEX project — run `forgex init` first.")

    user_req = request
    if file and file.is_file():
        user_req = file.read_text(encoding="utf-8")

    config = load_config(root)
    with open_stores(root) as stores:
        engine = BuildEngine(
            stores=stores,
            config=config,
            approval=make_approval(ui),
            progress=lambda line: ui.text(format_progress(line, rich_mode=(ui.mode is Output.RICH))),
        )
        result = asyncio.run(engine.run(user_req, dry_run=dry_run, resume=resume))

    if isinstance(result, DryRunReport):
        ui.data(result.model_dump(mode="json"))
        ui.ok(f"Dry run preview: {len(result.planned_tasks)} planned tasks, {len(result.planned_files)} files.")
        for t in result.planned_tasks:
            ui.text(f"  - [{t.get('priority')}] {t.get('id')}: {t.get('description')}")
        return

    ui.data(result.model_dump(mode="json"))
    if ui.mode in (Output.RICH, Output.PLAIN):
        if result.status == "completed":
            _render_success(ui, result)
        else:
            _render_failure(ui, result)

    raise typer.Exit(code=0 if result.status == "completed" else 1)
