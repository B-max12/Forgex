"""`forgex verify` — deterministic verification harness (tests/build/lint)."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer

from forgex.cli.ui import JsonFlag, PlainFlag, make_approval, ui_from
from forgex.config import load_config
from forgex.orchestration.stores import open_stores
from forgex.schemas.agent import AgentRole
from forgex.schemas.error import ProjectError
from forgex.tools import create_context
from forgex.tools.verification import run_verification
from forgex.utils.paths import find_project_root


def verify_command(
    ctx: typer.Context,
    no_build: Annotated[bool, typer.Option("--no-build", help="Skip the build step.")] = False,
    no_lint: Annotated[bool, typer.Option("--no-lint", help="Skip the lint step.")] = False,
    json_out: JsonFlag = False,
    plain: PlainFlag = False,
) -> None:
    """Run tests, build, and lint — deterministic, no LLM."""
    ui = ui_from(ctx, json_out=json_out, plain=plain)
    root = find_project_root()
    if root is None:
        raise ProjectError("Not inside a FORGEX project — run `forgex init` first.")

    config = load_config(root)
    with open_stores(root) as stores:
        tool_ctx = create_context(
            workspace=root,
            config=config,
            events=stores.recorder,
            approval=make_approval(ui),
            agent=AgentRole.SUPERVISOR,
        )
        outcome = asyncio.run(
            run_verification(
                root=root,
                executor=tool_ctx.executor,
                events=stores.recorder,
                include_build=not no_build,
                include_lint=not no_lint,
            )
        )

    ui.data(outcome.model_dump(mode="json"))
    steps = [("Tests", outcome.tests), ("Build", outcome.build), ("Lint", outcome.lint)]
    for name, step in steps:
        if step is None:
            ui.text(f"{name:<6} — not detected / not configured")
        elif step.ok:
            ui.ok(f"{name:<6} {' '.join(step.command)}")
        else:
            ui.error(f"{name:<6} FAILED (exit {step.exit_code}{', timed out' if step.timed_out else ''})")
            if step.output_tail:
                ui.text(step.output_tail[-1500:])

    ran = [s for _, s in steps if s is not None]
    raise typer.Exit(code=0 if all(s.ok for s in ran) else 1)
