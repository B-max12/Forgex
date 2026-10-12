"""`forgex supervise` — full supervision: verification + LLM audit + quality gates."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer
from rich.markup import escape

from forgex.agents.supervisor import supervise
from forgex.cli.ui import JsonFlag, Output, PlainFlag, make_approval, ui_from
from forgex.config import load_config
from forgex.orchestration.stores import open_stores
from forgex.schemas.error import ProjectError
from forgex.utils.paths import find_project_root


def supervise_command(
    ctx: typer.Context,
    no_build: Annotated[bool, typer.Option("--no-build", help="Skip the build step.")] = False,
    no_lint: Annotated[bool, typer.Option("--no-lint", help="Skip the lint step.")] = False,
    json_out: JsonFlag = False,
    plain: PlainFlag = False,
) -> None:
    """Inspect → diagnose → instruct repair."""
    ui = ui_from(ctx, json_out=json_out, plain=plain)
    root = find_project_root()
    if root is None:
        raise ProjectError("Not inside a FORGEX project — run `forgex init` first.")

    config = load_config(root)
    with open_stores(root) as stores:
        report = asyncio.run(
            supervise(
                stores=stores,
                config=config,
                approval=make_approval(ui),
                include_build=not no_build,
                include_lint=not no_lint,
            )
        )

    ui.data(report.model_dump(mode="json"))
    color = {"pass": "green", "fail": "red", "needs_review": "yellow"}.get(report.status, "white")
    if ui.mode is Output.RICH:
        ui.console.print(f"[bold {color}]VERDICT: {report.status.upper()}[/bold {color}]")
    else:
        ui.text(f"VERDICT: {report.status.upper()}")

    ui.text(report.summary)
    for item in report.errors:
        ui.text(f"  error: {escape(item)}")
    for item in report.warnings:
        ui.text(f"  warning: {escape(item)}")
    if report.required_changes:
        ui.text("  Required changes:")
        for change in report.required_changes:
            ui.text(f"    - {escape(change)}")

    raise typer.Exit(code=0 if report.status == "pass" else 1)
