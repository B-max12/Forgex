"""`forgex plan` — run the Architect agent standalone (spec sections 7, 34)."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer
from rich.markup import escape
from rich.table import Table

from forgex.agents.architect import build_planner, plan_project
from forgex.cli.ui import JsonFlag, Output, PlainFlag, ui_from
from forgex.config import load_config
from forgex.orchestration.stores import open_stores
from forgex.research.citations import format_note
from forgex.schemas.error import ProjectError
from forgex.schemas.plan import specs_to_tasks
from forgex.utils.paths import find_project_root

STAGE_LABELS = {
    "analyzing": "Analyzing request & repository",
    "researching": "Researching dependencies",
    "planning": "Producing implementation plan",
}


def plan_command(
    ctx: typer.Context,
    request: Annotated[str, typer.Argument(help="What should be built?")],
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show the plan without persisting anything.")] = False,
    json_out: JsonFlag = False,
    plain: PlainFlag = False,
) -> None:
    """Run the Architect agent: analysis, research, implementation plan."""
    ui = ui_from(ctx, json_out=json_out, plain=plain)
    root = find_project_root()
    if root is None:
        raise ProjectError("Not inside a FORGEX project — run `forgex init` first.")

    config = load_config(root)
    step = {"n": 0}

    status_ctx = None
    if ui.mode is Output.RICH:
        status_ctx = ui.console.status("[bold cyan][1/3] Analyzing request & repository...[/bold cyan]")
        status_ctx.start()

    def progress(stage: str) -> None:
        step["n"] += 1
        label = STAGE_LABELS.get(stage, stage)
        ui.text(f"[{step['n']}/3] {label}...")
        if status_ctx:
            status_ctx.update(f"[bold cyan][{step['n']}/3] {label} (waiting for model response)...[/bold cyan]")

    with open_stores(root) as stores:
        planner = build_planner(config=config, workspace=root, stores=stores)
        try:
            result = asyncio.run(
                plan_project(
                    planner,
                    stores=stores,
                    request=request,
                    dry_run=dry_run,
                    progress=progress,
                )
            )
        finally:
            if status_ctx:
                status_ctx.stop()
            aclose = getattr(planner, "aclose", None)
            if aclose is not None:
                asyncio.run(aclose())

    tasks = specs_to_tasks(result.plan.tasks)
    ui.data({
        "request": request,
        "plan": result.plan.model_dump(mode="json"),
        "research": [note.model_dump(mode="json") for note in result.research],
        "tasks_created": len(tasks),
        "persisted": not dry_run,
    })

    suffix = " (dry run — nothing persisted)" if dry_run else ""
    ui.ok(f"Plan created — {len(tasks)} tasks, {len(result.plan.libraries)} libraries{suffix}")

    if ui.mode is Output.RICH:
        table = Table(show_header=True, header_style="bold", expand=False)
        table.add_column("ID")
        table.add_column("Priority")
        table.add_column("Deps")
        table.add_column("Description", overflow="fold")
        for task in tasks:
            table.add_row(
                task.id,
                task.priority.value,
                ", ".join(task.depends_on) or "—",
                escape(task.description),
            )
        ui.console.print(table)
        if result.plan.libraries:
            ui.text(f"Libraries: {', '.join(escape(lib) for lib in result.plan.libraries)}")
        if result.research:
            ui.text("")
            ui.text("Research:")
            for note in result.research:
                ui.text(f"  {escape(format_note(note))}")
    elif ui.mode is Output.PLAIN:
        for task in tasks:
            deps = ",".join(task.depends_on) or "-"
            ui.text(f"{task.id} [{task.priority.value}] {task.description} (deps: {deps})")
        for note in result.research:
            ui.text(format_note(note))
