"""`forgex logs` — inspect the project event stream (spec section 24)."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Annotated

import typer
from rich.markup import escape

from forgex.cli.ui import JsonFlag, Output, PlainFlag, ui_from
from forgex.orchestration.events import read_events
from forgex.schemas.error import ConfigError, ProjectError
from forgex.schemas.event import Event, EventType
from forgex.utils.paths import find_project_root


def _pairs(event: Event, width: int = 60) -> str:
    parts = []
    for key, value in event.data.items():
        text = str(value).replace("\n", " ")
        if len(text) > width:
            text = text[: width - 1] + "…"
        parts.append(f"{key}={text}")
    return " ".join(parts)


def _render(event: Event, *, rich: bool) -> str:
    ts = event.ts.strftime("%H:%M:%S")
    run = f" run={event.run_id[:8]}" if event.run_id else ""
    pairs = _pairs(event)
    if rich:
        return (
            f"[dim]{ts}[/dim] [bold cyan]{event.type.value}[/bold cyan]"
            f"[dim]{escape(run)} {escape(pairs)}[/dim]"
        ).rstrip()
    return f"{ts} {event.type.value}{run} {pairs}".rstrip()


def _follow(events_path: Path, event_type: EventType | None, ui) -> None:
    """Poll JSONL and print appended events until interrupted."""
    with events_path.open("r", encoding="utf-8") as fh:
        fh.seek(0, os.SEEK_END)
        while True:
            line = fh.readline()
            if not line:
                time.sleep(0.5)
                continue
            line = line.strip()
            if not line:
                continue
            try:
                event = Event.from_jsonl(line)
            except Exception:  # noqa: BLE001
                continue
            if event_type is not None and event.type is not event_type:
                continue
            if ui.mode is Output.JSON:
                ui.console.print(event.model_dump_json(), soft_wrap=True, highlight=False)
            else:
                ui.console.print(_render(event, rich=(ui.mode is Output.RICH)))


def logs_command(
    ctx: typer.Context,
    event_type: Annotated[str | None, typer.Option("--type", "-t", help="Filter by EventType name.")] = None,
    limit: Annotated[int | None, typer.Option("--limit", "-n", help="Limit event count (default: all).")] = None,
    follow: Annotated[bool, typer.Option("--follow", "-f", help="Follow event stream in real-time.")] = False,
    json_out: JsonFlag = False,
    plain: PlainFlag = False,
) -> None:
    """Show recorded FORGEX events."""
    ui = ui_from(ctx, json_out=json_out, plain=plain)
    root = find_project_root()
    if root is None:
        raise ProjectError("Not inside a FORGEX project — run `forgex init` first.")

    etype = None
    if event_type:
        try:
            etype = EventType(event_type)
        except ValueError:
            valid = ", ".join(e.value for e in EventType)
            raise ConfigError(f"Unknown event type '{event_type}'. Valid: {valid}") from None

    events_path = root / ".forgex" / "events.jsonl"
    if not events_path.is_file():
        return

    if follow:
        _follow(events_path, etype, ui)
        return

    events = read_events(events_path, limit=limit, event_type=etype)
    if ui.mode is Output.JSON:
        for e in events:
            ui.console.print(e.model_dump_json(), soft_wrap=True, highlight=False)
    else:
        for e in events:
            ui.console.print(_render(e, rich=(ui.mode is Output.RICH)))
