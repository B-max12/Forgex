"""`forgex init` — scaffold the .forgex directory and detect the project."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from forgex.cli.ui import JsonFlag, PlainFlag, ui_from
from forgex.orchestration.state import StateStore
from forgex.project import detect_project, initialize_project


def init_command(
    ctx: typer.Context,
    name: Annotated[str | None, typer.Argument(help="Target directory (defaults to current).")] = None,
    json_out: JsonFlag = False,
    plain: PlainFlag = False,
) -> None:
    """Initialize FORGEX in a project directory."""
    ui = ui_from(ctx, json_out=json_out, plain=plain)
    target = Path(name).resolve() if name else Path.cwd()

    root = initialize_project(target)
    detection = detect_project(root)
    state = StateStore(root).load()

    ui.data({
        "root": str(root),
        "project_id": state.project_id if state else None,
        "detection": detection.as_dict(),
    })
    ui.ok(f"Initialized FORGEX project at {root}")
    if state:
        ui.text(f"Project ID: {state.project_id[:8]}")
    ui.text(f"Detected: {detection.summary()}")
    if detection.has_git:
        ui.text("Git repository detected — checkpoints will be available.")
    else:
        ui.warn("No Git repository detected. Run 'git init' to enable checkpoints.")
