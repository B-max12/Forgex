"""`forgex fix` — verify → supervise → repair until green (spec sections 12, 22)."""

from __future__ import annotations

import asyncio

import typer

from forgex.cli.build_views import _render_failure, _render_success, format_progress
from forgex.cli.ui import JsonFlag, Output, PlainFlag, make_approval, ui_from
from forgex.config import load_config
from forgex.orchestration.engine import BuildEngine
from forgex.orchestration.stores import open_stores
from forgex.schemas.error import ProjectError
from forgex.utils.paths import find_project_root


def fix_command(
    ctx: typer.Context,
    json_out: JsonFlag = False,
    plain: PlainFlag = False,
) -> None:
    """Run verification + supervision + the repair loop. No rebuild."""
    ui = ui_from(ctx, json_out=json_out, plain=plain)
    root = find_project_root()
    if root is None:
        raise ProjectError("Not inside a FORGEX project — run `forgex init` first.")

    config = load_config(root)
    with open_stores(root) as stores:
        engine = BuildEngine(
            stores=stores,
            config=config,
            approval=make_approval(ui),
            progress=lambda line: ui.text(format_progress(line, rich_mode=(ui.mode is Output.RICH))),
        )
        result = asyncio.run(engine.fix())

    ui.data(result.model_dump(mode="json"))
    if ui.mode in (Output.RICH, Output.PLAIN):
        if result.status == "completed":
            _render_success(ui, result)
        else:
            _render_failure(ui, result)

    raise typer.Exit(code=0 if result.status == "completed" else 1)
