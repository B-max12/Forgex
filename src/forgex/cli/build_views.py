"""Shared output formatters for build and fix commands."""

from __future__ import annotations

from rich.markup import escape
from rich.panel import Panel

from forgex.cli.ui import UI, Output
from forgex.orchestration.engine import BuildRunResult


def _tests_line(result: BuildRunResult) -> str:
    tests = result.tests
    if tests is None:
        return "not run"
    if tests.passed is None:
        return f"exit {tests.exit_code}"
    return f"{tests.passed} passed, {tests.failed or 0} failed"


def format_progress(line: str, *, rich_mode: bool) -> str:
    """Format an agent progress message with modern terminal styling."""
    if not rich_mode:
        return line
    styled = line
    if "Architect:" in line:
        styled = line.replace("Architect:", "[bold cyan]● [Architect][/bold cyan]")
    elif "Plan created:" in line:
        styled = f"[green]✓[/green] [bold]{line}[/bold]"
    elif "Builder:" in line or "Task " in line:
        styled = line.replace("Builder:", "[bold blue]● [Builder][/bold blue]")
    elif "FAILED" in line:
        styled = f"[red]✗[/red] {line}"
    elif "Supervisor:" in line:
        styled = line.replace("Supervisor:", "[bold magenta]● [Supervisor][/bold magenta]")
    elif "Self-healing" in line:
        styled = f"[bold yellow]⟳ {line}[/bold yellow]"
    elif "Testing" in line or "quality verification" in line:
        styled = f"[bold yellow]● [Verification][/bold yellow] {line}"
    return styled


def _render_success(ui: UI, result: BuildRunResult) -> None:
    if ui.mode is Output.RICH:
        ui.console.print(Panel("[bold green]FORGEX BUILD COMPLETE[/bold green]", expand=False))
    lines = [
        f"Tasks       {result.tasks_completed}/{result.tasks_total}",
        f"Files       {len(result.changed_files)} changed",
        f"Tests       {_tests_line(result)}",
        f"Build       {'passed' if result.build_ok else 'failed' if result.build_ok is False else '—'}",
        f"Supervisor  {result.verdict}",
        f"Iterations  {result.iterations}",
        f"Checkpoint  {result.checkpoint[:8] if result.checkpoint else '—'}",
    ]
    if result.usage:
        prompt_tok = result.usage.get("prompt_tokens") or 0
        comp_tok = result.usage.get("completion_tokens") or 0
        cost = result.usage.get("estimated_cost_usd")
        if prompt_tok > 0 or comp_tok > 0:
            cost_str = f" (${cost:.4f})" if cost is not None else ""
            lines.append(f"Tokens      {prompt_tok:,} in / {comp_tok:,} out{cost_str}")
    for line in lines:
        ui.text(line)
    if result.changed_files and ui.mode in (Output.RICH, Output.PLAIN):
        ui.text("")
        ui.text("Changed files:")
        for path in result.changed_files[:30]:
            ui.text(f"  {escape(path)}")
    for warning in result.warnings:
        ui.warn(warning)


def _render_failure(ui: UI, result: BuildRunResult) -> None:
    if ui.mode is Output.RICH:
        ui.console.print(Panel(f"[bold red]FORGEX BUILD FAILED[/bold red]\n{result.reason}", expand=False))
    else:
        ui.error(f"FORGEX BUILD FAILED: {result.reason}")

    lines = [
        f"Tasks       {result.tasks_completed}/{result.tasks_total}",
        f"Remaining   {', '.join(result.remaining_tasks) or 'none'}",
        f"Tests       {_tests_line(result)}",
        f"Supervisor  {result.verdict}",
        f"Iterations  {result.iterations}",
    ]
    if result.usage:
        prompt_tok = result.usage.get("prompt_tokens") or 0
        comp_tok = result.usage.get("completion_tokens") or 0
        cost = result.usage.get("estimated_cost_usd")
        if prompt_tok > 0 or comp_tok > 0:
            cost_str = f" (${cost:.4f})" if cost is not None else ""
            lines.append(f"Tokens      {prompt_tok:,} in / {comp_tok:,} out{cost_str}")
    for line in lines:
        ui.text(line)
