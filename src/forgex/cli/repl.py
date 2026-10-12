"""Persistent interactive REPL for FORGEX."""

from __future__ import annotations

import os
import shlex
import sys
from pathlib import Path
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from forgex import __version__
from forgex.cli.intent import IntentAction, classify_intent
from forgex.cli.session import Session
from forgex.config.loader import global_config_path
from forgex.schemas.error import ForgexError

BANNER = r"""[bold cyan]
███████╗ ██████╗ ██████╗  ██████╗ ███████╗██╗  ██╗
██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝╚██╗██╔╝
█████╗  ██║   ██║██████╔╝██║  ███╗█████╗   ╚███╔╝ 
██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝   ██╔██╗ 
██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗██╔╝ ██╗
╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝[/bold cyan]
[dim]Persistent Adaptive Multi-Model Software Engineering CLI[/dim]
[dim]Plan. Build. Refine. Verify.  (v{version})[/dim]
"""

COMMANDS = [
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

    def __init__(self, session: Session | None = None) -> None:
        self.session = session or Session()
        self.console = Console()
        hist_dir = Path.home() / ".forgex"
        hist_dir.mkdir(parents=True, exist_ok=True)
        self.history_file = hist_dir / "repl_history"
        self.prompt_session: PromptSession = PromptSession(
            history=FileHistory(str(self.history_file)),
            completer=WordCompleter(COMMANDS + SLASH_COMMANDS, ignore_case=True),
            style=PROMPT_STYLE,
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
                    self._run_cli_command(["config", "setup"])

    def print_help(self) -> None:
        """Display help table for available commands."""
        table = Table(title="FORGEX Commands & Workflows", border_style="cyan", show_header=True)
        table.add_column("Command", style="bold cyan", width=20)
        table.add_column("Description")

        workflows = [
            ("plan <goal>", "Architectural planning, research, and task decomposition"),
            ("build", "Execute full build pipeline: plan → build → review → verify → repair"),
            ("fix", "Verify, supervise, and auto-repair until green without full rebuild"),
            ("review", "Senior engineer review of diff and recent changes"),
            ("verify", "Deterministic verification (tests, lint, typecheck)"),
            ("supervise", "Run verification + code audit + soft gates verdict"),
            ("status", "Project state, task breakdown, git branch, and token usage"),
            ("diff", "Inspect current uncommitted git changes"),
            ("checkpoint [msg]", "Create reversible snapshot of codebase state"),
            ("rollback [id]", "Reversibly rollback to a checkpoint"),
            ("init [dir]", "Initialize FORGEX in current or target directory"),
            ("models [catalog|health]", "Inspect configured models, catalog, and provider status"),
            ("tools [list|run]", "Inspect and manually execute system tools"),
            ("config [show|get|set|setup]", "View or modify persistent configuration"),
            ("doctor", "Validate environment, dependencies, and connectivity"),
            ("cd <dir>", "Switch directory and auto-attach project"),
            ("clear", "Clear terminal screen"),
            ("exit / quit", "Exit the interactive session"),
        ]
        for cmd, desc in workflows:
            table.add_row(cmd, desc)

        self.console.print(table)
        self.console.print("\n[dim]Tip: You can also enter plain English prompts, e.g. [italic]build me a JWT auth service[/italic][/dim]\n")

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

        tokens = shlex.split(text)
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
            target = args[0] if args else str(Path.home())
            if not self.session.change_directory(target):
                self.console.print(f"[red]Directory not found: {target}[/red]")
            else:
                self.console.print(f"[dim]Switched to {Path.cwd()}[/dim]")
            return

        # Commands that do not accept positional words: if followed by prose (e.g. "build me a ...",
        # "fix the failing ..."), treat as natural language rather than CLI syntax.
        nl_commands = {"build", "fix", "verify", "supervise", "status", "doctor", "diff", "logs"}
        if cmd in nl_commands and len(tokens) > 1 and not tokens[1].startswith("-"):
            pass
        elif cmd in COMMANDS:
            self._run_cli_command(tokens)
            return

        # Natural language intent fallback
        intent = classify_intent(text)
        if intent.action != IntentAction.UNKNOWN and intent.confidence >= 0.5:
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
        """Invoke a Typer CLI command within the REPL session."""
        from typer.testing import CliRunner

        from forgex.cli.app import app

        runner = CliRunner()
        success = False
        try:
            result = runner.invoke(app, args, catch_exceptions=True)
            if result.output:
                # Print output directly
                sys.stdout.write(result.output)
                sys.stdout.flush()
            if result.exit_code != 0 and result.exception:
                if isinstance(result.exception, ForgexError):
                    self.console.print(f"[red]✗[/red] {result.exception}")
                elif not isinstance(result.exception, SystemExit):
                    self.console.print(f"[red]Error:[/red] {result.exception}")
            success = result.exit_code == 0
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
