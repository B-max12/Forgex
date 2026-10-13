"""Terminal output adapter (spec section 23).

All user-facing output goes through :class:`UI` so the modes required by
spec section 23 (``--plain`` / ``--json`` / ``--quiet``) behave
consistently across every command.
"""

from __future__ import annotations

import json
import sys
from enum import Enum
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.prompt import Confirm
from rich.theme import Theme

_THEME = Theme(
    {
        "forgex.title": "bold cyan",
        "forgex.ok": "green",
        "forgex.warn": "yellow",
        "forgex.err": "red",
        "forgex.muted": "dim",
    }
)


class Output(str, Enum):
    RICH = "rich"
    PLAIN = "plain"
    JSON = "json"
    QUIET = "quiet"


JsonFlag = Annotated[bool, typer.Option("--json", help="Machine-readable JSON output.")]
PlainFlag = Annotated[bool, typer.Option("--plain", help="Plain output (CI/SSH safe).")]


class UI:
    def __init__(self, mode: Output, console: Console | None = None) -> None:
        self.mode = mode
        if console is not None:
            self.console = console
        elif mode is Output.JSON:
            self.console = Console(theme=_THEME, soft_wrap=True, highlight=False)
        else:
            self.console = Console(theme=_THEME)

    def ok(self, message: str) -> None:
        if self.mode is Output.QUIET or self.mode is Output.JSON:
            return
        if self.mode is Output.RICH:
            self.console.print(f"[green]✓[/green] {message}")
        else:
            self.console.print(f"OK: {message}")

    def warn(self, message: str) -> None:
        if self.mode is Output.QUIET or self.mode is Output.JSON:
            return
        if self.mode is Output.RICH:
            self.console.print(f"[yellow]![/yellow] {message}")
        else:
            self.console.print(f"WARN: {message}")

    def error(self, message: str) -> None:
        if self.mode is Output.JSON:
            return
        if self.mode is Output.RICH:
            self.console.print(f"[red]✗[/red] {message}")
        else:
            self.console.print(f"ERROR: {message}")

    def text(self, message: str) -> None:
        if self.mode is Output.QUIET or self.mode is Output.JSON:
            return
        self.console.print(message)

    def data(self, payload: dict[str, Any]) -> None:
        if self.mode is Output.JSON:
            self.console.print(json.dumps(payload, indent=2, default=str), soft_wrap=True, highlight=False)


def ui_from(
    ctx: typer.Context,
    *,
    json_out: bool = False,
    plain: bool = False,
) -> UI:
    obj = ctx.obj or {}
    if json_out or obj.get("json"):
        mode = Output.JSON
    elif plain or obj.get("plain"):
        mode = Output.PLAIN
    elif obj.get("quiet"):
        mode = Output.QUIET
    else:
        mode = Output.RICH

    return UI(mode=mode)


def make_approval(ui: UI):
    """Interactive approval callback (spec section 33)."""

    def approve(description: str) -> bool:
        if ui.mode is not Output.RICH or not sys.stdin.isatty():
            return False
        return Confirm.ask(f"FORGEX wants to: {description}\nAllow?", default=False)

    return approve
