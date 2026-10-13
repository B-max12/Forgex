"""`forgex run` — run the project (spec section 22)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated

import typer

from forgex.cli.ui import JsonFlag, Output, PlainFlag, make_approval, ui_from
from forgex.config import load_config
from forgex.orchestration.stores import open_stores
from forgex.schemas.agent import AgentRole
from forgex.schemas.error import ProjectError
from forgex.tools import create_context
from forgex.utils.paths import find_project_root


def detect_run_command(root: Path) -> list[str] | None:
    pkg = root / "package.json"
    if pkg.is_file():
        try:
            scripts = json.loads(pkg.read_text(encoding="utf-8")).get("scripts") or {}
        except (OSError, ValueError):
            return None
        if scripts.get("start"):
            return ["npm", "start"]
    return None


def run_command(
    ctx: typer.Context,
    command: Annotated[list[str] | None, typer.Argument(help="Command to run (default: detected npm start).")] = None,
    timeout: Annotated[int | None, typer.Option("--timeout", help="Seconds before run is killed.")] = None,
    json_out: JsonFlag = False,
    plain: PlainFlag = False,
) -> None:
    """Run the project's start command through the policy-gated executor."""
    ui = ui_from(ctx, json_out=json_out, plain=plain)
    root = find_project_root()
    if root is None:
        raise ProjectError("Not inside a FORGEX project — run `forgex init` first.")

    cmd = list(command) if command else detect_run_command(root)
    if not cmd:
        raise ProjectError("No run command detected — pass one: forgex run -- python main.py")

    config = load_config(root)
    with open_stores(root) as stores:
        tool_ctx = create_context(
            workspace=root,
            config=config,
            events=stores.recorder,
            approval=make_approval(ui),
            agent=AgentRole.BUILDER,
        )
        result = asyncio.run(tool_ctx.executor.run(cmd, cwd=".", timeout=timeout))

    ui.data({
        "command": result.argv,
        "exit_code": result.exit_code,
        "timed_out": result.timed_out,
        "duration_ms": round(result.duration_ms, 1),
    })

    if ui.mode is not Output.JSON and ui.mode is not Output.QUIET:
        ui.text(f"$ {' '.join(result.argv)}")
        if result.stdout:
            ui.text(result.stdout.rstrip())
        if result.stderr:
            ui.text(result.stderr.rstrip())

    raise typer.Exit(code=0 if result.exit_code == 0 and not result.timed_out else 1)
