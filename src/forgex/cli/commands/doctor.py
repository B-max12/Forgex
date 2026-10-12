"""`forgex doctor` — environment, tools, and configuration health checks (spec section 37)."""

from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from forgex import __version__
from forgex.cli.ui import JsonFlag, Output, PlainFlag, ui_from
from forgex.config import global_config_path, load_config
from forgex.models.router import collect_health
from forgex.schemas.error import ConfigError
from forgex.utils.paths import find_project_root


@dataclass
class Check:
    name: str
    ok: bool
    required: bool
    detail: str


def _check_python() -> Check:
    v = sys.version_info
    ok = (v.major, v.minor) >= (3, 12)
    return Check(
        "Python",
        ok,
        required=True,
        detail=f"{v.major}.{v.minor}.{v.micro} (>= 3.12 required)",
    )


def _check_binary(name: str, *, required: bool, purpose: str) -> Check:
    found = shutil.which(name) is not None
    detail = f"found — {purpose}" if found else f"not found — {purpose}"
    return Check(name, found, required=required, detail=detail)


def _check_docker(config) -> list[Check]:
    found = shutil.which("docker") is not None
    sandbox_on = config is not None and config.sandbox.enabled
    purpose = "sandboxed execution" + (" (ENABLED)" if sandbox_on else " (disabled)")
    checks = [Check("Docker", found, required=sandbox_on, detail=f"found — {purpose}" if found else f"not found — {purpose}")]
    if sandbox_on and found:
        image = config.sandbox.image
        try:
            proc = subprocess.run(
                ["docker", "image", "inspect", image],
                capture_output=True,
                timeout=15,
                check=False,
            )
            ok = proc.returncode == 0
            detail = f"image {image} present" if ok else f"image missing — run: docker pull {image}"
        except (OSError, subprocess.TimeoutExpired):
            ok, detail = False, "docker daemon unreachable"
        checks.append(Check("Sandbox image", ok, required=False, detail=detail))
    return checks


def _check_credentials(config) -> list[Check]:
    checks = []
    for name, p_cfg in sorted(config.providers.items()):
        env_var = p_cfg.api_key_env
        if not env_var:
            continue
        val = os.environ.get(env_var)
        checks.append(
            Check(
                f"Credential: {env_var}",
                bool(val),
                required=False,
                detail=f"configured for provider '{name}'" if val else f"not set in environment (used by {name})",
            )
        )
    return checks


def _check_workspace(root: Path) -> Check:
    return Check("Workspace", root.is_dir(), required=True, detail=str(root))


def _check_sqlite() -> Check:
    try:
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE t (x INT);")
        conn.close()
    except Exception as exc:  # noqa: BLE001
        return Check("SQLite", False, required=True, detail=str(exc))
    return Check("SQLite", True, required=True, detail="available (metadata storage)")


def doctor_command(
    ctx: typer.Context,
    json_out: JsonFlag = False,
    plain: PlainFlag = False,
    ping: Annotated[bool, typer.Option("--ping", help="Also ping configured providers (network).")] = False,
) -> None:
    """Check environment, tools and configuration."""
    ui = ui_from(ctx, json_out=json_out, plain=plain)
    root = find_project_root() or Path.cwd()

    try:
        config = load_config(root)
        config_error = None
    except ConfigError as exc:
        config, config_error = None, str(exc)

    checks = [
        _check_python(),
        _check_binary("git", required=False, purpose="checkpoints and diffs"),
        _check_binary("rg", required=False, purpose="fast code search (falls back to Python)"),
    ]
    checks.extend(_check_docker(config))

    if config is not None:
        gpath = global_config_path()
        ppath = root / ".forgex" / "config.toml" if find_project_root() else None
        sources = []
        if gpath.is_file():
            sources.append("global")
        if ppath and ppath.is_file():
            sources.append("project")
        detail = "valid — " + (", ".join(sources) if sources else "defaults")
        checks.append(Check("Configuration", True, required=True, detail=detail))
        checks.extend(_check_credentials(config))
    else:
        checks.append(Check("Configuration", False, required=True, detail=config_error or "invalid"))

    checks.append(_check_workspace(root))
    checks.append(_check_sqlite())

    if ping and config is not None:
        for name, health in sorted(collect_health(config).items()):
            checks.append(Check(f"Provider: {name}", health.ok, required=False, detail=health.detail))

    all_required_ok = all(c.ok for c in checks if c.required)
    ui.data({
        "forgex": __version__,
        "root": str(root),
        "ok": all_required_ok,
        "checks": [asdict(c) for c in checks],
    })

    if ui.mode is Output.RICH:
        table = Table(show_header=True, header_style="bold", expand=False)
        table.add_column("Check", style="bold")
        table.add_column("Status")
        table.add_column("Detail", overflow="fold")
        for c in checks:
            if c.ok:
                status = "[green]✓[/green]"
            elif c.required:
                status = "[red]✗[/red]"
            else:
                status = "[yellow]○[/yellow] optional"
            table.add_row(c.name, status, c.detail)
        ui.console.print(table)
    elif ui.mode is Output.PLAIN:
        for c in checks:
            label = "OK" if c.ok else ("FAIL" if c.required else "WARN")
            ui.console.print(f"{label}: {c.name} — {c.detail}")

    raise typer.Exit(code=0 if all_required_ok else 1)
