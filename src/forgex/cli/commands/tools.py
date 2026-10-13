"""`forgex tools` — inspect and manually run tools (agent debugging surface)."""

from __future__ import annotations

import asyncio
import json
from typing import Annotated

import typer
from rich.table import Table

from forgex.cli.ui import JsonFlag, Output, PlainFlag, make_approval, ui_from
from forgex.config import load_config
from forgex.orchestration.stores import open_stores
from forgex.sandbox.permissions import permission_set_for
from forgex.schemas.agent import AgentRole
from forgex.schemas.error import ConfigError, PermissionDeniedError, ProjectError
from forgex.tools import ToolCall, ToolExecutor, ToolResult, build_tool_registry, create_context
from forgex.utils.paths import find_project_root

app = typer.Typer(no_args_is_help=True, help="Inspect and manually run FORGEX tools.")


@app.command("list")
def list_command(
    ctx: typer.Context,
    json_out: JsonFlag = False,
    plain: PlainFlag = False,
) -> None:
    """List all tools with their required permissions."""
    ui = ui_from(ctx, json_out=json_out, plain=plain)
    registry = build_tool_registry()
    payload = [
        {
            "name": t.name,
            "description": t.description,
            "permissions": sorted(p.value for p in t.required_permissions),
            "parameters": t.parameters_schema(),
        }
        for t in registry.tools()
    ]
    ui.data({"tools": payload})
    if ui.mode is Output.RICH:
        table = Table(show_header=True, header_style="bold")
        table.add_column("Tool")
        table.add_column("Permissions")
        table.add_column("Description", overflow="fold")
        for item in payload:
            perms_str = ", ".join(item["permissions"]) if isinstance(item["permissions"], list) else str(item["permissions"])
            table.add_row(str(item["name"]), perms_str or "—", str(item["description"]))
        ui.console.print(table)
    elif ui.mode is Output.PLAIN:
        for item in payload:
            perms_str = ",".join(item["permissions"]) if isinstance(item["permissions"], list) else str(item["permissions"])
            ui.console.print(f"{item['name']} [{perms_str}]: {item['description']}")


@app.command("run")
def run_command(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Tool name, e.g. read_file")],
    agent: Annotated[str, typer.Option("--agent", "-a", help="Act as this agent role.")] = "builder",
    args_json: Annotated[str | None, typer.Option("--args", help="JSON object of tool arguments.")] = "{}",
    json_out: JsonFlag = False,
    plain: PlainFlag = False,
) -> None:
    """Run one tool as one agent."""
    ui = ui_from(ctx, json_out=json_out, plain=plain)
    root = find_project_root()
    if root is None:
        raise ProjectError("Not inside a FORGEX project — run `forgex init` first.")

    try:
        role = AgentRole(agent)
    except ValueError as exc:
        valid = ", ".join(r.value for r in AgentRole)
        raise ConfigError(f"Unknown agent role '{agent}'. Valid: {valid}") from exc

    try:
        arguments = json.loads(args_json or "{}")
        if not isinstance(arguments, dict):
            raise TypeError("args must be a JSON object")
    except Exception as exc:
        raise ConfigError(f"--args must be a valid JSON object: {exc}") from exc

    config = load_config(root)
    registry = build_tool_registry()
    with open_stores(root) as stores:
        tool_ctx = create_context(
            workspace=root,
            config=config,
            events=stores.recorder,
            approval=make_approval(ui),
            agent=role,
        )
        executor = ToolExecutor(
            registry=registry,
            permissions=permission_set_for(role),
            context=tool_ctx,
        )
        try:
            result = asyncio.run(executor.execute(ToolCall(name=name, arguments=arguments)))
        except PermissionDeniedError as exc:
            result = ToolResult(ok=False, denied=True, error=str(exc))

    payload = {
        "tool": name,
        "agent": role.value,
        "ok": result.ok,
        "denied": result.denied,
        "error": result.error,
        "output": result.output,
        "data": result.data,
    }
    ui.console.print(json.dumps(payload, indent=2, default=str), soft_wrap=True, highlight=False)
    raise typer.Exit(code=0 if result.ok else 1)
