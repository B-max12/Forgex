"""`forgex context` — inspect the context index and retrieval (spec section 17)."""

from __future__ import annotations

from typing import Annotated, Optional

import typer
from rich.table import Table

from forgex.cli.ui import JsonFlag, Output, PlainFlag, ui_from
from forgex.context.manager import ContextManager
from forgex.schemas.error import ProjectError
from forgex.utils.paths import find_project_root

app = typer.Typer(no_args_is_help=True, help="Inspect the project context index.")


@app.command("stats")
def stats_command(
    ctx: typer.Context,
    refresh: Annotated[bool, typer.Option("--refresh", help="Force a full re-index.")] = False,
    json_out: JsonFlag = False,
    plain: PlainFlag = False,
) -> None:
    """Index summary: files, languages, symbols, cache stats."""
    ui = ui_from(ctx, json_out=json_out, plain=plain)
    root = find_project_root()
    if root is None:
        raise ProjectError("Not inside a FORGEX project — run `forgex init` first.")

    manager = ContextManager(root)
    index = manager.ensure_index(refresh=refresh)
    languages: dict[str, int] = {}
    symbols = 0
    imports = 0
    for entry in index.files.values():
        languages[entry.language] = languages.get(entry.language, 0) + 1
        symbols += len(entry.symbols)
        imports += len(entry.imports)

    payload = {
        "files": len(index.files),
        "languages": languages,
        "symbols": symbols,
        "imports": imports,
        "stats": index.stats,
    }
    ui.data(payload)

    if ui.mode is Output.RICH:
        table = Table(show_header=True, header_style="bold")
        table.add_column("Metric")
        table.add_column("Value")
        table.add_row("Total Files", str(len(index.files)))
        table.add_row("Languages", ", ".join(f"{k}: {v}" for k, v in languages.items()))
        table.add_row("Symbols", str(symbols))
        table.add_row("Imports", str(imports))
        table.add_row("Cache Stats", str(index.stats))
        ui.console.print(table)
    elif ui.mode is Output.PLAIN:
        ui.text(f"Files: {len(index.files)} | Symbols: {symbols} | Imports: {imports} | Stats: {index.stats}")


@app.command("search")
def search_command(
    ctx: typer.Context,
    query: Annotated[str, typer.Option("--query", "-q", help="Search query")] = "",
    seeds: Annotated[Optional[list[str]], typer.Option("--seeds", "-s", help="Seed file paths")] = None,
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max results")] = 10,
    json_out: JsonFlag = False,
    plain: PlainFlag = False,
) -> None:
    """Relevance search across project files."""
    ui = ui_from(ctx, json_out=json_out, plain=plain)
    root = find_project_root()
    if root is None:
        raise ProjectError("Not inside a FORGEX project — run `forgex init` first.")

    manager = ContextManager(root)
    ranked = manager.relevant_files(query=query, seeds=seeds or [], limit=limit)
    payload = [{"path": r.path, "score": r.score, "reasons": r.reasons} for r in ranked]
    ui.data({"results": payload})

    if ui.mode is Output.RICH:
        table = Table(show_header=True, header_style="bold")
        table.add_column("Score", style="cyan")
        table.add_column("Path")
        table.add_column("Reasons", overflow="fold")
        for r in ranked:
            table.add_row(str(r.score), r.path, "; ".join(r.reasons))
        ui.console.print(table)
    elif ui.mode is Output.PLAIN:
        for r in ranked:
            ui.text(f"[{r.score}] {r.path}: {'; '.join(r.reasons)}")
