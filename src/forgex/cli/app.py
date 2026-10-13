"""Typer application assembly and the controlled-error entry point."""

from __future__ import annotations

import os
import sys
from typing import Annotated

from typer._click import Command, Context
import typer
from rich.console import Console

from forgex import __version__
from forgex.cli.commands import (
    build as build_cmd,
)
from forgex.cli.commands import (
    checkpoint as checkpoint_cmd,
)
from forgex.cli.commands import (
    config as config_cmd,
)
from forgex.cli.commands import (
    context as context_cmd,
)
from forgex.cli.commands import (
    diff as diff_cmd,
)
from forgex.cli.commands import (
    do_cmd,
)
from forgex.cli.commands import (
    doctor as doctor_cmd,
)
from forgex.cli.commands import (
    fix as fix_cmd,
)
from forgex.cli.commands import (
    init as init_cmd,
)
from forgex.cli.commands import (
    logs as logs_cmd,
)
from forgex.cli.commands import (
    models as models_cmd,
)
from forgex.cli.commands import (
    plan as plan_cmd,
)
from forgex.cli.commands import (
    review as review_cmd,
)
from forgex.cli.commands import (
    rollback as rollback_cmd,
)
from forgex.cli.commands import (
    run as run_cmd,
)
from forgex.cli.commands import (
    status as status_cmd,
)
from forgex.cli.commands import (
    supervise as supervise_cmd,
)
from forgex.cli.commands import (
    task as task_cmd,
)
from forgex.cli.commands import (
    tools as tools_cmd,
)
from forgex.cli.commands import (
    verify as verify_cmd,
)
from forgex.cli.repl import start_repl
from forgex.config.loader import load_env_files
from forgex.schemas.error import ForgexError
from forgex.utils.logging import configure_logging
from forgex.utils.paths import find_project_root


class ForgexTyperGroup(typer.core.TyperGroup):
    """Custom TyperGroup that routes unrecognized command inputs to autonomous execution."""

    def resolve_command(
        self, ctx: Context, args: list[str]
    ) -> tuple[str | None, Command | None, list[str]]:
        if not args:
            return super().resolve_command(ctx, args)
        cmd_name = args[0]
        # Registered commands or options start with '-'
        if cmd_name in self.commands or cmd_name.startswith("-"):
            return super().resolve_command(ctx, args)
        # Unrecognized command / natural language prose -> route to 'do' with full args
        cmd = self.get_command(ctx, "do")
        return "do", cmd, args

    def get_command(self, ctx: Context, cmd_name: str) -> Command | None:
        cmd = super().get_command(ctx, cmd_name)
        if cmd is not None:
            return cmd
        if not cmd_name.startswith("-") and "do" in self.commands:
            return self.commands["do"]
        return None


app = typer.Typer(
    cls=ForgexTyperGroup,
    name="forgex",
    help="FORGEX — autonomous multi-agent AI software engineering. Plan. Build. Refine. Verify.",
    no_args_is_help=False,
    add_completion=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"forgex {__version__}")
        raise typer.Exit


@app.callback(invoke_without_command=True)
def root(
    ctx: typer.Context,
    version: Annotated[bool | None, typer.Option("--version", callback=_version_callback, is_eager=True, help="Show version and exit.")] = None,
    no_repl: Annotated[bool, typer.Option("--no-repl", help="Do not start interactive REPL when no command given.")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Verbose logging.")] = False,
    quiet: Annotated[bool, typer.Option("--quiet", help="Suppress non-essential output.")] = False,
    json_out: Annotated[bool, typer.Option("--json", help="Machine-readable JSON output.")] = False,
    plain: Annotated[bool, typer.Option("--plain", help="Plain output (CI/SSH safe).")] = False,
    debug: Annotated[bool, typer.Option("--debug", help="Show full tracebacks on errors.")] = False,
    offline: Annotated[bool, typer.Option("--offline", help="Offline mode: no web research, no remote providers.")] = False,
) -> None:
    """FORGEX — an AI software engineering team for your terminal."""
    if offline:
        os.environ["FORGEX_OFFLINE"] = "1"
    if debug:
        os.environ["FORGEX_DEBUG"] = "1"

    load_env_files(find_project_root())
    configure_logging(level="debug" if verbose else "warning")
    ctx.obj = {"verbose": verbose, "quiet": quiet, "json": json_out, "plain": plain}

    if ctx.invoked_subcommand is None:
        import sys

        if no_repl or not sys.stdin.isatty():
            typer.echo(ctx.get_help())
            raise typer.Exit()
        start_repl()
        raise typer.Exit()


def repl_command() -> None:
    """Start interactive persistent REPL session."""
    start_repl()


# Register all commands
app.command(name="repl", help="Start interactive persistent REPL session.")(repl_command)
app.command(name="init", help="Initialize FORGEX in a project directory.")(init_cmd.init_command)
app.command(name="doctor", help="Check environment, tools and configuration.")(doctor_cmd.doctor_command)
app.command(name="status", help="Show project status.")(status_cmd.status_command)
app.add_typer(config_cmd.app, name="config", help="View and modify configuration.")
app.command(name="logs", help="Show recorded FORGEX events.")(logs_cmd.logs_command)
app.add_typer(models_cmd.app, name="models", help="Inspect model bindings, catalog, and provider health.")
app.add_typer(tools_cmd.app, name="tools", help="Inspect and manually run FORGEX tools.")
app.command(name="plan", help="Run the Architect: analysis, research, implementation plan.")(plan_cmd.plan_command)
app.add_typer(task_cmd.app, name="task", help="Inspect and execute plan tasks.")
app.command(name="checkpoint", help="Create a Git checkpoint of the current state.")(checkpoint_cmd.checkpoint_command)
app.command(name="rollback", help="Roll back to a checkpoint (reversible).")(rollback_cmd.rollback_command)
app.command(name="diff", help="Show the current Git diff.")(diff_cmd.diff_command)
app.command(name="review", help="Expert review of recent changes.")(review_cmd.review_command)
app.command(name="verify", help="Run tests/build/lint — deterministic, no LLM.")(verify_cmd.verify_command)
app.command(name="supervise", help="Full supervision: verification + audit + verdict.")(supervise_cmd.supervise_command)
app.command(name="build", help="Full build: plan → build → review → verify → supervise → repair loop.")(build_cmd.build_command)
app.command(name="fix", help="Verify, supervise, and repair until green — no rebuild.")(fix_cmd.fix_command)
app.command(name="do", help="Autonomous execution: auto-init → plan → build → verify → repair → checkpoint.")(do_cmd.do_command)
app.command(name="run", help="Run the project's start command.")(run_cmd.run_command)
app.add_typer(context_cmd.app, name="context", help="Inspect the context index and retrieval.")

REGISTERED_COMMANDS = {
    "repl",
    "init",
    "doctor",
    "status",
    "config",
    "logs",
    "models",
    "tools",
    "plan",
    "task",
    "checkpoint",
    "rollback",
    "diff",
    "review",
    "verify",
    "supervise",
    "build",
    "fix",
    "run",
    "context",
    "do",
}


def main() -> None:
    """Console-script entry point with controlled error handling."""
    # Natural language command line routing:
    # If user invokes `forgex "add auth"` or `forgex build me a bot`, route to `do` command.
    if len(sys.argv) > 1:
        first = sys.argv[1].lower()
        if not first.startswith("-") and first not in REGISTERED_COMMANDS or first == "build" and len(sys.argv) > 2 and not any(a.startswith("-") for a in sys.argv[2:]):
            sys.argv = [sys.argv[0], "do", *sys.argv[1:]]

    try:
        app()
    except ForgexError as exc:
        if os.environ.get("FORGEX_DEBUG"):
            raise
        Console(stderr=True).print(f"[red]✗[/red] {exc}")
        raise SystemExit(exc.exit_code) from None
    except KeyboardInterrupt:
        Console(stderr=True).print("[yellow]Interrupted — on-disk state is preserved.[/yellow]")
        raise SystemExit(130) from None
    except Exception as exc:
        if os.environ.get("FORGEX_DEBUG"):
            raise
        err = Console(stderr=True)
        err.print(f"[red]✗[/red] internal error: {type(exc).__name__}: {exc}")
        err.print("[dim]re-run with --debug for the full traceback[/dim]")
        raise SystemExit(70) from None
