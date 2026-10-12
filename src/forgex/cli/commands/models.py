"""`forgex models` — inspect agent bindings, catalog, and provider health."""

from __future__ import annotations

import os
from typing import Annotated

import typer
from rich.table import Table

from forgex.cli.ui import JsonFlag, Output, PlainFlag, ui_from
from forgex.config import load_config
from forgex.models.registry import ModelRegistry
from forgex.models.router import collect_health
from forgex.schemas.agent import AgentRole
from forgex.utils.paths import find_project_root

app = typer.Typer(help="Inspect model bindings, catalog, and provider health.")


def _binding_rows(config) -> list[dict]:
    rows = []
    models_cfg = config.models
    for role in AgentRole:
        binding = getattr(models_cfg, role.value, None)
        if not binding:
            continue
        prov_cfg = config.providers.get(binding.provider)
        model = binding.model or (prov_cfg.default_model if prov_cfg else None) or "—"
        env_var = prov_cfg.api_key_env if prov_cfg else None
        cred = "set" if (env_var and os.environ.get(env_var)) else ("keyless" if not env_var else "missing")
        rows.append({
            "agent": role.value,
            "provider": binding.provider,
            "model": model,
            "credential": cred,
        })
    return rows


@app.callback(invoke_without_command=True)
def models_default(
    ctx: typer.Context,
    json_out: JsonFlag = False,
    plain: PlainFlag = False,
) -> None:
    if ctx.invoked_subcommand is not None:
        return
    ui = ui_from(ctx, json_out=json_out, plain=plain)
    root = find_project_root()
    config = load_config(root)
    rows = _binding_rows(config)

    ensemble_reviewers = None
    if config.ensemble.enabled:
        from forgex.agents.ensemble import resolve_reviewer_bindings
        ensemble_reviewers = [f"{b.provider}/{b.model}" for b in resolve_reviewer_bindings(config)]

    ui.data({"bindings": rows, "ensemble": ensemble_reviewers})
    if ui.mode is Output.RICH:
        table = Table(show_header=True, header_style="bold")
        table.add_column("Agent")
        table.add_column("Provider")
        table.add_column("Model")
        table.add_column("Credential")
        for r in rows:
            table.add_row(r["agent"], r["provider"], r["model"], r["credential"])
        ui.console.print(table)
        if ensemble_reviewers:
            ui.text(f"Ensemble reviewers: {', '.join(ensemble_reviewers)}")
    elif ui.mode is Output.PLAIN:
        for r in rows:
            ui.text(f"{r['agent']}: {r['provider']}/{r['model']} ({r['credential']})")
        if ensemble_reviewers:
            ui.text(f"Ensemble reviewers: {', '.join(ensemble_reviewers)}")


@app.command("catalog")
def catalog_command(
    ctx: typer.Context,
    json_out: JsonFlag = False,
    plain: PlainFlag = False,
) -> None:
    """Show the advisory model capability catalog."""
    ui = ui_from(ctx, json_out=json_out, plain=plain)
    root = find_project_root()
    config = load_config(root)
    reg = ModelRegistry(config.models.capabilities)
    catalog = reg.catalog()
    payload = [c.model_dump() for c in catalog]
    ui.data({"catalog": payload})

    if ui.mode is Output.RICH:
        table = Table(show_header=True, header_style="bold")
        table.add_column("Model")
        table.add_column("Context")
        table.add_column("Tools")
        table.add_column("JSON")
        table.add_column("Stream")
        for c in catalog:
            table.add_row(
                c.model,
                str(c.context_window or "—"),
                "✓" if c.supports_tools else "—",
                "✓" if c.supports_json else "—",
                "✓" if c.supports_streaming else "—",
            )
        ui.console.print(table)
    elif ui.mode is Output.PLAIN:
        for c in catalog:
            ui.text(f"{c.model}: ctx={c.context_window} tools={c.supports_tools} json={c.supports_json}")


@app.command("health")
def health_command(
    ctx: typer.Context,
    json_out: JsonFlag = False,
    plain: PlainFlag = False,
) -> None:
    """Live ping of all configured providers."""
    ui = ui_from(ctx, json_out=json_out, plain=plain)
    root = find_project_root()
    config = load_config(root)
    health_results = collect_health(config)

    all_ok = all(h.ok for h in health_results.values())
    payload = {name: h.model_dump() for name, h in health_results.items()}
    ui.data({"ok": all_ok, "providers": payload})

    if ui.mode is Output.RICH:
        table = Table(show_header=True, header_style="bold")
        table.add_column("Provider")
        table.add_column("Status")
        table.add_column("Detail")
        table.add_column("Latency")
        for name, h in sorted(health_results.items()):
            status = "[green]✓[/green]" if h.ok else "[red]✗[/red]"
            lat = f"{h.latency_ms:.0f}ms" if h.latency_ms is not None else "—"
            table.add_row(name, status, h.detail, lat)
        ui.console.print(table)
    elif ui.mode is Output.PLAIN:
        for name, h in sorted(health_results.items()):
            ui.text(f"{name}: {'OK' if h.ok else 'FAIL'} ({h.detail})")

    raise typer.Exit(code=0 if all_ok else 1)
