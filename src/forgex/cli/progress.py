"""Rich terminal progress and summary rendering for FORGEX Universal CLI."""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table


def render_pipeline_header(request: str, console: Console | None = None) -> None:
    """Print an eye-catching start header for an autonomous build run."""
    c = console or Console()
    c.print(
        Panel(
            f"[bold cyan]Task:[/bold cyan] {request}\n"
            "[dim]Autonomous Pipeline: Auto-Init ➔ Plan ➔ Build ➔ Verify ➔ Repair ➔ Checkpoint[/dim]",
            title="[bold green]FORGEX Autonomous Execution[/bold green]",
            border_style="cyan",
        )
    )


def render_runtime_summary(
    result: Any,
    console: Console | None = None,
) -> None:
    """Render a comprehensive result panel after autonomous pipeline completion."""
    c = console or Console()

    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="dim", justify="right")
    grid.add_column()

    # Status
    if result.status == "completed":
        status_text = "[bold green]✔ SUCCESS[/bold green] (Verified & Approved)"
        border = "green"
    else:
        status_text = f"[bold red]✖ FAILED[/bold red] ({result.reason or 'Unresolved errors'})"
        border = "red"

    grid.add_row("Outcome:", status_text)
    grid.add_row("Task Request:", f"[bold white]{result.request}[/bold white]")

    # Tasks
    tasks_text = f"{result.tasks_completed}/{result.tasks_total} completed"
    if result.tasks_completed == result.tasks_total and result.tasks_total > 0:
        tasks_text = f"[green]{tasks_text}[/green]"
    grid.add_row("Tasks Executed:", tasks_text)

    # Changed files
    if result.changed_files:
        files_text = f"{len(result.changed_files)} file(s) modified/created"
        grid.add_row("Code Changes:", files_text)

    # Verification / Tests
    if result.tests:
        t = result.tests
        test_summary = f"[green]{t.passed} passed[/green]"
        if t.failed > 0:
            test_summary += f", [red]{t.failed} failed[/red]"
        if t.skipped > 0:
            test_summary += f", [yellow]{t.skipped} skipped[/yellow]"
        grid.add_row("Deterministic Tests:", test_summary)

    # Build status
    if result.build_ok is not None:
        build_str = "[green]Passing[/green]" if result.build_ok else "[red]Failing[/red]"
        grid.add_row("Build/Typecheck:", build_str)

    # Checkpoint
    if result.checkpoint_id:
        grid.add_row("Git Checkpoint:", f"[cyan]{result.checkpoint_id[:8]}[/cyan] [dim](reversible snapshot)[/dim]")

    # Duration
    if getattr(result, "duration_seconds", 0) > 0:
        grid.add_row("Pipeline Duration:", f"{result.duration_seconds:.1f}s")

    # Token & Cost Usage
    if getattr(result, "usage", None):
        u = result.usage
        prompt_t = u.get("prompt_tokens", 0)
        compl_t = u.get("completion_tokens", 0)
        cost = u.get("cost_usd", 0.0)
        grid.add_row(
            "Model Usage:",
            f"{prompt_t:,} prompt + {compl_t:,} completion tokens [dim](${cost:.4f})[/dim]",
        )

    title = "[bold green]Autonomous Run Complete[/bold green]" if result.is_success else "[bold red]Autonomous Run Incomplete[/bold red]"
    c.print(Panel(grid, title=title, border_style=border))

    # Show list of files if any
    if result.changed_files:
        c.print("[dim]Modified files:[/dim]")
        for f in result.changed_files[:10]:
            c.print(f"  [dim]•[/dim] [cyan]{f}[/cyan]")
        if len(result.changed_files) > 10:
            c.print(f"  [dim]... and {len(result.changed_files) - 10} more files[/dim]")
