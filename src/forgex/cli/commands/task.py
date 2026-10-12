"""`forgex task` — inspect and execute plan tasks (Builder surface)."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer
from rich.markup import escape
from rich.table import Table

from forgex.agents.builder import build_builder, execute_task
from forgex.cli.ui import JsonFlag, Output, PlainFlag, make_approval, ui_from
from forgex.config import load_config
from forgex.orchestration.state import TaskStore
from forgex.orchestration.stores import open_stores
from forgex.schemas.error import ProjectError
from forgex.schemas.task import ready_tasks
from forgex.utils.paths import find_project_root

app = typer.Typer(no_args_is_help=True, help="Inspect and execute plan tasks.")


@app.command("list")
def list_command(
    ctx: typer.Context,
    json_out: JsonFlag = False,
    plain: PlainFlag = False,
) -> None:
    """List tasks with status and readiness."""
    ui = ui_from(ctx, json_out=json_out, plain=plain)
    root = find_project_root()
    if root is None:
        raise ProjectError("Not inside a FORGEX project — run `forgex init` first.")

    tasks = TaskStore(root).load()
    ready_ids = {t.id for t in ready_tasks(tasks)}
    payload = [
        {
            "id": t.id,
            "status": t.status.value,
            "priority": t.priority.value,
            "depends_on": t.depends_on,
            "attempts": t.attempts,
            "ready": t.id in ready_ids,
            "description": t.description,
        }
        for t in tasks
    ]
    ui.data({"tasks": payload})

    if ui.mode is Output.RICH:
        table = Table(show_header=True, header_style="bold")
        table.add_column("ID")
        table.add_column("Status")
        table.add_column("Priority")
        table.add_column("Deps")
        table.add_column("Ready")
        table.add_column("Description", overflow="fold")
        for item in payload:
            ready_str = "[green]✓[/green]" if item["ready"] else "[yellow]—[/yellow]"
            table.add_row(
                item["id"],
                item["status"],
                item["priority"],
                ", ".join(item["depends_on"]) or "—",
                ready_str,
                escape(item["description"]),
            )
        ui.console.print(table)
    elif ui.mode is Output.PLAIN:
        for item in payload:
            ui.console.print(f"{item['id']} [{item['status']}] ready={item['ready']}: {item['description']}")


@app.command("run")
def run_command(
    ctx: typer.Context,
    task_id: Annotated[str, typer.Argument(help="Task ID to execute, e.g. TASK-001")],
    json_out: JsonFlag = False,
    plain: PlainFlag = False,
) -> None:
    """Execute one task with the Builder agent."""
    ui = ui_from(ctx, json_out=json_out, plain=plain)
    root = find_project_root()
    if root is None:
        raise ProjectError("Not inside a FORGEX project — run `forgex init` first.")

    config = load_config(root)
    with open_stores(root) as stores:
        tasks = stores.tasks.load()
        task = next((t for t in tasks if t.id == task_id), None)
        if task is None:
            raise ProjectError(f"Task '{task_id}' not found in tasks.json")

        state = stores.state.load()
        if not state or not state.architecture_plan:
            raise ProjectError("No architecture plan found in project state. Run `forgex plan` first.")

        builder = build_builder(
            config=config,
            workspace=root,
            stores=stores,
            approval=make_approval(ui),
            run_id=state.current_run_id,
        )
        try:
            result = asyncio.run(
                execute_task(
                    task,
                    builder=builder,
                    stores=stores,
                    config=config,
                    plan=state.architecture_plan,
                    research=state.research,
                )
            )
        finally:
            asyncio.run(builder.aclose())

    ui.data({
        "task_id": task_id,
        "status": result.status,
        "summary": result.summary,
        "changed_files": result.changed_files,
        "issues": result.issues,
    })

    if result.status == "completed":
        ui.ok(f"Task {task_id} completed: {result.summary}")
    else:
        ui.error(f"Task {task_id} failed: {result.summary}")

    raise typer.Exit(code=0 if result.status == "completed" else 1)
