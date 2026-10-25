"""Persistent interactive REPL for FORGEX."""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
import sys
from pathlib import Path
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.input import DummyInput, create_input
from prompt_toolkit.output import DummyOutput, create_output
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from forgex import __version__
from forgex.cli.intent import IntentAction, classify_intent
from forgex.cli.progress import render_pipeline_header, render_runtime_summary
from forgex.cli.runtime import AutonomousRuntime
from forgex.cli.session import Session
from forgex.config.loader import global_config_path
from forgex.schemas.error import ForgexError

logger = logging.getLogger("forgex.repl")

BANNER = r"""[bold cyan]
███████╗ ██████╗ ██████╗  ██████╗ ███████╗██╗  ██╗
██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝╚██╗██╔╝
█████╗  ██║   ██║██████╔╝██║  ███╗█████╗   ╚███╔╝
██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝   ██╔██╗
██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗██╔╝ ██╗
╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝[/bold cyan]
[dim]Autonomous Adaptive Multi-Model Software Engineering CLI[/dim]
[dim]Just describe what you want. We Plan, Build, Verify & Repair.  (v{version})[/dim]
"""

COMMANDS = [
    "do",
    "init",
    "plan",
    "build",
    "fix",
    "review",
    "verify",
    "supervise",
    "status",
    "doctor",
    "models",
    "tools",
    "checkpoint",
    "rollback",
    "diff",
    "config",
    "logs",
    "task",
    "context",
    "run",
    "cd",
    "clear",
    "help",
    "exit",
    "quit",
]

SLASH_COMMANDS = [f"/{cmd}" for cmd in COMMANDS]

PROMPT_STYLE = Style.from_dict(
    {
        "brand": "#00d7ff bold",
        "project": "#00ff87 bold",
        "unattached": "#ffd700 dim",
        "sep": "#666666",
        "arrow": "#00ff87 bold",
    }
)


class ForgexREPL:
    """Interactive persistent shell session for FORGEX."""

    def __init__(
        self,
        session: Session | None = None,
        *,
        output: Any = None,
        input: Any = None,
    ) -> None:
        self.session = session or Session()
        self.console = Console()
        hist_dir = Path.home() / ".forgex"
        try:
            hist_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            logger.debug("Could not create history directory %s: %s", hist_dir, exc)
        self.history_file = hist_dir / "repl_history"

        # Safe input/output initialization to support headless CI & Windows non-console buffers
        try:
            pt_output = output or create_output()
        except Exception as exc:
            logger.debug("Using DummyOutput fallback: %s", exc)
            pt_output = DummyOutput()

        try:
            pt_input = input or create_input()
        except Exception as exc:
            logger.debug("Using DummyInput fallback: %s", exc)
            pt_input = DummyInput()

        try:
            self.prompt_session: PromptSession = PromptSession(
                history=FileHistory(str(self.history_file)),
                completer=WordCompleter(COMMANDS + SLASH_COMMANDS, ignore_case=True),
                style=PROMPT_STYLE,
                output=pt_output,
                input=pt_input,
            )
        except Exception as exc:
            logger.warning("PromptSession initialization failed, falling back to dummy session: %s", exc)
            self.prompt_session = PromptSession(
                output=DummyOutput(),
                input=DummyInput(),
            )

    def print_banner(self) -> None:
        """Display the welcome banner and session overview."""
        self.console.print(BANNER.format(version=__version__))

        grid = Table.grid(padding=(0, 2))
        grid.add_column(style="dim")
        grid.add_column()

        proj_display = (
            f"[bold green]{self.session.project_root.name}[/bold green] [dim]({self.session.project_root})[/dim]"
            if self.session.is_attached and self.session.project_root
            else "[bold yellow]None[/bold yellow] [dim](Type 'init' or 'cd <dir>' to attach)[/dim]"
        )
        grid.add_row("Attached Project:", proj_display)

        arch_model = f"{self.session.config.models.architect.provider}:{self.session.config.models.architect.model}"
        grid.add_row("Default Model:", f"[cyan]{arch_model}[/cyan]")
        grid.add_row("Permissions:", f"[magenta]{self.session.config.permissions.mode}[/magenta]")
        if os.environ.get("FORGEX_OFFLINE") == "1":
            grid.add_row("Network:", "[red]Offline mode active[/red]")

        self.console.print(Panel(grid, title="[bold]Session Context[/bold]", border_style="cyan"))
        self.console.print("[dim]Type [bold white]help[/bold white] for commands, or describe what to build in plain English.[/dim]\n")

    def check_first_run(self) -> None:
        """Guide the user through onboarding if global config does not exist."""
        g_cfg = global_config_path()
        if not g_cfg.is_file():
            self.console.print(
                Panel(
                    "[bold yellow]First time using FORGEX?[/bold yellow]\n\n"
                    "No global configuration was found at ~/.forgex/config.toml.\n"
                    "Let's configure your AI model provider and local profile.",
                    border_style="yellow",
                )
            )
            if sys.stdin.isatty():
                from rich.prompt import Confirm
                if Confirm.ask("Launch the guided setup wizard now?", default=True):
                    self._run_setup_wizard()

    def _run_setup_wizard(self) -> None:
        """Run the setup wizard directly (not through CliRunner) so it can read real stdin."""
        import typer
        import typer.core
        from forgex.cli.commands.config import setup_command

        try:
            # Create a typer Context — setup_command only needs ctx.obj for ui_from()
            ctx = typer.Context(typer.core.TyperCommand("setup"))
            ctx.obj = {"verbose": False, "quiet": False, "json": False, "plain": False}
            setup_command(ctx)
            self.session.refresh()
        except (KeyboardInterrupt, EOFError):
            self.console.print("\n[yellow]Setup cancelled.[/yellow]")
        except Exception as exc:
            self.console.print(f"[red]Setup error:[/red] {exc}")

    def print_help(self) -> None:
        """Display help table for natural language usage and power user commands."""
        self.console.print(
            Panel(
                "[bold white]Describe what you want to build in plain English:[/bold white]\n\n"
                "  [cyan]❯[/cyan] [green]Build me a REST API with FastAPI and SQLite[/green]\n"
                "  [cyan]❯[/cyan] [green]Add JWT authentication with refresh tokens[/green]\n"
                "  [cyan]❯[/cyan] [green]Fix the failing tests in users.py[/green]\n"
                "  [cyan]❯[/cyan] [green]Create a full-stack dashboard with React[/green]\n\n"
                "[dim]FORGEX will automatically initialize, plan, build, verify, repair, and checkpoint.[/dim]",
                title="[bold cyan]FORGEX Universal CLI — How It Works[/bold cyan]",
                border_style="cyan",
            )
        )

        table = Table(title="Power User Commands (Optional Granular Control)", border_style="dim", show_header=True)
        table.add_column("Command", style="bold cyan", width=22)
        table.add_column("Description")

        workflows = [
            ("do <request>", "Execute end-to-end autonomous pipeline directly"),
            ("plan <goal>", "Run only Architect: planning & task breakdown"),
            ("build", "Run build pipeline for existing plan tasks"),
            ("fix", "Auto-repair errors until tests pass — no rebuild"),
            ("verify", "Deterministic verification (tests, lint, typecheck)"),
            ("review", "Senior engineer code review of diff"),
            ("supervise", "Run verification + code audit + soft gates verdict"),
            ("status", "Project state, task breakdown, branch, and token usage"),
            ("diff", "Inspect current uncommitted git changes"),
            ("checkpoint [msg]", "Create reversible snapshot of codebase state"),
            ("rollback [id]", "Reversibly rollback to a checkpoint"),
            ("init [dir]", "Initialize FORGEX in current or target directory"),
            ("models [catalog|health]", "Inspect configured models and providers"),
            ("tools [list|run]", "Inspect and manually execute system tools"),
            ("config [show|set|setup]", "View or modify configuration"),
            ("doctor", "Validate environment, dependencies, and network"),
            ("cd <dir>", "Switch directory and auto-attach project"),
            ("clear", "Clear terminal screen"),
            ("exit / quit", "Exit the interactive session"),
        ]
        for cmd, desc in workflows:
            table.add_row(cmd, desc)

        self.console.print(table)

    def get_prompt_text(self) -> HTML:
        """Generate dynamic colored prompt based on session state."""
        if self.session.is_attached and self.session.project_root:
            name = self.session.project_root.name
            return HTML(f"<brand>forgex</brand> <sep>[</sep><project>{name}</project><sep>]</sep> <arrow>❯</arrow> ")
        return HTML("<brand>forgex</brand> <arrow>❯</arrow> ")

    def dispatch(self, raw_input: str) -> None:
        """Dispatch user input to built-ins, Typer commands, or natural language intent."""
        text = raw_input.strip()
        if not text:
            return

        self.session.history.append(text)

        # Strip optional leading slash
        if text.startswith("/"):
            text = text[1:].strip()

        # Strip optional leading 'forgex' if user typed 'forgex <cmd>' in REPL
        if text.lower().startswith("forgex "):
            text = text[7:].strip()

        tokens = shlex.split(text, posix=sys.platform != "win32")
        if not tokens:
            return

        cmd = tokens[0].lower()
        args = tokens[1:]

        # Handle built-ins
        if cmd in ("exit", "quit", "q"):
            raise EOFError
        if cmd in ("clear", "cls"):
            self.console.clear()
            return
        if cmd in ("help", "?"):
            self.print_help()
            return
        if cmd == "cd":
            raw_target = text[len(tokens[0]):].strip() if len(tokens) > 0 else ""
            if raw_target:
                target = raw_target.strip("'\"")
            else:
                target = str(Path.home())
            if not self.session.change_directory(target):
                self.console.print(f"[red]Directory not found: {target}[/red]")
            else:
                self.console.print(f"[dim]Switched to {Path.cwd()}[/dim]")
            return

        if cmd == "do" and len(tokens) > 1:
            req = " ".join(tokens[1:])
            self._run_autonomous(req, raw_input=text)
            return

        # Commands that do not accept positional words: if followed by prose (e.g. "build me a ...",
        # "fix the failing ..."), treat as natural language rather than CLI syntax.
        nl_commands = {"build", "fix", "verify", "supervise", "status", "doctor", "diff", "logs", "do"}
        if cmd in nl_commands and len(tokens) > 1 and not tokens[1].startswith("-"):
            pass
        elif cmd in COMMANDS:
            self._run_cli_command(tokens)
            return

        # Natural language intent classification
        intent = classify_intent(text)
        if intent.action == IntentAction.AUTONOMOUS:
            target_req = intent.raw_request or text
            effective_req = self.session.context.enrich_request(target_req)
            self._run_autonomous(effective_req, raw_input=text)
            return
        elif intent.action != IntentAction.UNKNOWN and intent.confidence >= 0.5:
            steps_desc = " → ".join(" ".join(step) for step in intent.pipeline)
            self.console.print(
                f"[bold cyan]Intent recognized:[/bold cyan] {intent.description}\n"
                f"[dim]Pipeline: {steps_desc}[/dim]"
            )
            self._run_pipeline(intent.pipeline)
        else:
            self.console.print(
                f"[yellow]Unrecognized command: '{cmd}'.[/yellow] "
                "Type [bold]help[/bold] for available commands or describe your task in plain English."
            )

    def _run_autonomous(self, request: str, raw_input: str) -> bool:
        """Run the end-to-end autonomous pipeline directly."""
        render_pipeline_header(request, console=self.console)
        runtime = AutonomousRuntime(session=self.session, ui=self.session.ui)
        try:
            result = asyncio.run(runtime.execute(request))
            render_runtime_summary(result, console=self.console)
            self.session.context.record_run(
                request=raw_input,
                status=result.status,
                changed_files=result.changed_files,
                checkpoint_id=result.checkpoint_id,
            )
            return result.is_success
        except KeyboardInterrupt:
            self.console.print("\n[yellow]Autonomous run cancelled by user.[/yellow]")
            return False
        except Exception as exc:
            self.console.print(f"[red]Autonomous run error:[/red] {exc}")
            return False
        finally:
            self.session.refresh()

    def _run_pipeline(self, pipeline: list[list[str]]) -> None:
        """Execute a pipeline of CLI commands sequentially, stopping on failure."""
        for i, step in enumerate(pipeline, start=1):
            if len(pipeline) > 1:
                self.console.print(f"\n[bold green]▶ Step {i}/{len(pipeline)}: {' '.join(step)}[/bold green]")
            ok = self._run_cli_command(step)
            if not ok:
                self.console.print(f"[red]Pipeline stopped due to error in step: {' '.join(step)}[/red]")
                break

    def _run_cli_command(self, args: list[str]) -> bool:
        """Invoke a Typer CLI command within the REPL session.

        Uses subprocess to run each command so that:
        1. Each command gets a fresh event loop (fixes 'Event loop is closed')
        2. Interactive prompts can read real stdin
        3. Rich output goes directly to the terminal
        """
        # Interactive commands that need real stdin must bypass CliRunner
        if args == ["config", "setup"]:
            self._run_setup_wizard()
            return True

        import subprocess

        success = False
        try:
            # Run as a subprocess so each command gets a fresh Python/asyncio state
            cmd = [sys.executable, "-m", "forgex", *args]
            result = subprocess.run(cmd, cwd=os.getcwd())
            success = result.returncode == 0
        except ForgexError as exc:
            self.console.print(f"[red]✗[/red] {exc}")
        except KeyboardInterrupt:
            self.console.print("\n[yellow]Operation cancelled by user.[/yellow]")
        except Exception as exc:  # noqa: BLE001
            self.console.print(f"[red]Unexpected error:[/red] {type(exc).__name__}: {exc}")
        finally:
            self.session.refresh()
        return success

    def run(self) -> None:
        """Main REPL loop."""
        self.print_banner()
        self.check_first_run()

        while True:
            try:
                line = self.prompt_session.prompt(self.get_prompt_text())
                self.dispatch(line)
            except KeyboardInterrupt:
                self.console.print("\n[yellow]^C (Use 'exit' or Ctrl+D to quit)[/yellow]")
                continue
            except EOFError:
                self.console.print("\n[dim]Goodbye! On-disk state is preserved.[/dim]")
                break


def start_repl(session: Session | None = None) -> None:
    """Entry point to launch the FORGEX REPL."""
    repl = ForgexREPL(session=session)
    repl.run()
