"""`forgex config` — view and modify layered configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.prompt import Confirm, Prompt

from forgex.cli.ui import JsonFlag, PlainFlag, ui_from
from forgex.config import (
    CONFIG_FILE_NAME,
    global_config_path,
    load_config,
    project_config_path,
    set_config_value,
    store_secret,
)
from forgex.schemas.error import ConfigError
from forgex.utils.paths import find_project_root

app = typer.Typer(no_args_is_help=True, help="View and modify FORGEX configuration.")

GlobalFlag = Annotated[
    bool,
    typer.Option("--global", "-g", help="Operate on ~/.forgex/config.toml instead of project config."),
]


def _target_path(global_: bool) -> Path:
    if global_:
        return global_config_path()
    root = find_project_root()
    if root is None:
        raise ConfigError("Not inside a FORGEX project. Use --global to edit global configuration.")
    return project_config_path(root)


def _get_dotted(data: dict[str, Any], dotted: str) -> Any:
    node: Any = data
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            raise ConfigError(f"Configuration key '{dotted}' not found")
        node = node[part]
    return node


@app.command("show")
def show_command(
    ctx: typer.Context,
    json_out: JsonFlag = False,
    plain: PlainFlag = False,
) -> None:
    """Show the currently active merged configuration."""
    ui = ui_from(ctx, json_out=json_out, plain=plain)
    root = find_project_root()
    config = load_config(root)
    payload = config.model_dump(mode="json", exclude_none=True)
    ui.data(payload)
    if not json_out and not ctx.obj.get("json"):
        ui.text(json.dumps(payload, indent=2))


@app.command("get")
def get_command(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="Dotted configuration key, e.g. workflow.max_iterations")],
    json_out: JsonFlag = False,
    plain: PlainFlag = False,
) -> None:
    """Get a configuration value by dotted key."""
    ui = ui_from(ctx, json_out=json_out, plain=plain)
    root = find_project_root()
    config = load_config(root)
    val = _get_dotted(config.model_dump(mode="json"), key)
    ui.data({"key": key, "value": val})
    if not json_out and not ctx.obj.get("json"):
        ui.text(str(val))


@app.command("set")
def set_command(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="Dotted configuration key, e.g. models.architect.model")],
    value: Annotated[str, typer.Argument(help="New value")],
    global_: GlobalFlag = False,
    json_out: JsonFlag = False,
    plain: PlainFlag = False,
) -> None:
    """Set a configuration value in project (or global) config.toml."""
    ui = ui_from(ctx, json_out=json_out, plain=plain)
    path = _target_path(global_)
    set_config_value(path, key, value)
    ui.data({"key": key, "value": value, "path": str(path)})
    ui.ok(f"Set {key} = {value} in {path}")


@dataclass
class ProviderSetupInfo:
    name: str
    type: str = "openai_compatible"
    base_url: str | None = None
    api_key_env: str | None = None
    api_key: str | None = None
    timeout_seconds: float = 120.0


@dataclass
class SetupAnswers:
    provider: str | None = None
    base_url: str | None = None
    api_key_env: str | None = None
    api_key: str | None = None
    models: dict[str, str] = field(default_factory=dict)
    providers: list[ProviderSetupInfo] = field(default_factory=list)
    role_bindings: dict[str, tuple[str, str]] = field(default_factory=dict)
    sandbox_enabled: bool = False
    approval_mode: str = "ask"


def apply_setup(answers: SetupAnswers, *, global_dir: Path) -> None:
    import os
    path = global_dir / CONFIG_FILE_NAME

    providers = list(answers.providers)
    if answers.provider:
        providers.append(
            ProviderSetupInfo(
                name=answers.provider,
                base_url=answers.base_url,
                api_key_env=answers.api_key_env,
                api_key=answers.api_key,
            )
        )

    for p in providers:
        set_config_value(path, f"providers.{p.name}.type", p.type)
        if p.base_url:
            set_config_value(path, f"providers.{p.name}.base_url", p.base_url)
        if p.api_key_env:
            set_config_value(path, f"providers.{p.name}.api_key_env", p.api_key_env)
        set_config_value(path, f"providers.{p.name}.timeout_seconds", p.timeout_seconds)

        if p.api_key and p.api_key_env:
            store_secret(p.api_key_env, p.api_key, global_dir=global_dir)
            os.environ[p.api_key_env] = p.api_key

    role_bindings = dict(answers.role_bindings)
    if answers.models:
        for r, m in answers.models.items():
            role_bindings[r] = (answers.provider or "groq", str(m))

    for role, (prov, model) in role_bindings.items():
        set_config_value(path, f"models.{role}.provider", prov)
        set_config_value(path, f"models.{role}.model", str(model))

    set_config_value(path, "sandbox.enabled", "true" if answers.sandbox_enabled else "false")
    set_config_value(path, "permissions.mode", answers.approval_mode)


def _test_provider_connectivity(provider: str, base_url: str | None, api_key: str | None) -> tuple[bool, str]:
    """Perform a lightweight test request to verify API connectivity."""
    import httpx

    url = (base_url or ("https://api.groq.com/openai/v1" if provider == "groq" else "https://api.openai.com/v1")).rstrip("/") + "/models"
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(url, headers=headers)
            if resp.status_code in (200, 201):
                return True, "Connection verified (HTTP 200)"
            return False, f"Provider returned HTTP {resp.status_code}"
    except Exception as exc:
        return False, str(exc)


def _strip_quotes(value: str) -> str:
    """Strip surrounding single or double quotes from user input."""
    v = value.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
        return v[1:-1]
    return v


def _fetch_models(base_url: str, api_key: str | None) -> list[str]:
    """Fetch the list of available model IDs from an OpenAI-compatible /models endpoint."""
    import httpx

    url = base_url.rstrip("/") + "/models"
    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        with httpx.Client(timeout=8.0) as client:
            resp = client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                models = data.get("data", [])
                return sorted([m["id"] for m in models if isinstance(m, dict) and "id" in m])
    except Exception:
        pass
    return []


@app.command("setup")
def setup_command(
    ctx: typer.Context,
) -> None:
    """Interactive setup wizard for provider credentials and defaults."""
    import os
    from rich.console import Console
    from rich.table import Table

    console = Console()
    ui = ui_from(ctx)
    ui.text("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    ui.text("FORGEX Configuration Setup Wizard — Welcome!")
    ui.text("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    ui.text("Security & Terms Notice:")
    ui.text(" • FORGEX operates locally and executes developer tools.")
    ui.text(" • Reversible checkpoints are created before file edits.")
    ui.text(" • API keys are stored with restricted permissions (0600) in ~/.forgex/.env.")
    ui.text(" • You control permissions via mode: ask (default), auto, or safe.\n")

    # Step 1: Up to 4 providers sequentially
    configured_providers: list[ProviderSetupInfo] = []
    g_dir = global_config_path().parent

    ui.text("[bold]Step 1: Provider Setup[/bold] — Configure 1 to 4 providers (Groq, NVIDIA, OpenAI, OpenRouter, Local, Custom)")

    for idx in range(1, 5):
        if idx > 1:
            ui.text("")
            if not Confirm.ask(f"Add another provider? ({idx}/4)", default=False):
                break

        ui.text(f"\n[cyan]── Provider {idx}/4 ──[/cyan]")
        default_choice = "groq" if idx == 1 else ("nvidia" if idx == 2 else "openai")
        prov = Prompt.ask(
            f"Choose provider #{idx}",
            choices=["groq", "nvidia", "openai", "openrouter", "local", "custom"],
            default=default_choice,
        )

        name = prov
        ptype = "openai_compatible"
        base_url = ""
        api_key_env: str | None = None
        api_key: str | None = None

        if prov == "groq":
            name = "groq" if not any(p.name == "groq" for p in configured_providers) else f"groq_{idx}"
            ptype = "groq"
            base_url = "https://api.groq.com/openai/v1"
            api_key_env = "FORGEX_GROQ_API_KEY"
            api_key = _strip_quotes(Prompt.ask(f"Enter Groq API key for {name} (gsk_...)", password=True, default=""))
        elif prov == "nvidia":
            name = "nvidia" if not any(p.name == "nvidia" for p in configured_providers) else f"nvidia_{idx}"
            ptype = "openai_compatible"
            base_url = "https://integrate.api.nvidia.com/v1"
            api_key_env = "FORGEX_NVIDIA_API_KEY"
            api_key = _strip_quotes(Prompt.ask(f"Enter NVIDIA API key for {name} (nvapi-...)", password=True, default=""))
        elif prov == "openai":
            name = "openai_compatible" if not any(p.name == "openai_compatible" for p in configured_providers) else f"openai_{idx}"
            ptype = "openai_compatible"
            base_url = "https://api.openai.com/v1"
            api_key_env = "FORGEX_OPENAI_API_KEY"
            api_key = _strip_quotes(Prompt.ask(f"Enter OpenAI API key for {name} (sk-...)", password=True, default=""))
        elif prov == "openrouter":
            name = "openrouter" if not any(p.name == "openrouter" for p in configured_providers) else f"openrouter_{idx}"
            ptype = "openai_compatible"
            base_url = "https://openrouter.ai/api/v1"
            api_key_env = "FORGEX_OPENROUTER_API_KEY"
            api_key = _strip_quotes(Prompt.ask(f"Enter OpenRouter API key for {name} (sk-or-...)", password=True, default=""))
        elif prov == "local":
            name = "local" if not any(p.name == "local" for p in configured_providers) else f"local_{idx}"
            ptype = "local"
            base_url = _strip_quotes(Prompt.ask("Enter local OpenAI-compatible endpoint", default="http://localhost:11434/v1"))
            api_key_env = None
            api_key = None
        else:  # custom
            name = _strip_quotes(Prompt.ask("Enter custom provider name", default=f"custom_{idx}"))
            ptype = "openai_compatible"
            base_url = _strip_quotes(Prompt.ask("Enter base URL", default="http://localhost:8080/v1"))
            api_key_env = f"FORGEX_{name.upper()}_API_KEY"
            api_key = _strip_quotes(Prompt.ask("Enter API key (if required)", password=True, default=""))

        # Test connectivity
        ui.text(f"Testing connectivity to {name}...")
        ok, detail = _test_provider_connectivity(name, base_url, api_key)
        if ok:
            ui.ok(f"✓ {name} connection verified: {detail}")
        else:
            ui.warn(f"⚠ {name} test: {detail} (proceeding)")

        # Persist secret immediately
        if api_key and api_key_env:
            store_secret(api_key_env, api_key, global_dir=g_dir)
            os.environ[api_key_env] = api_key

        configured_providers.append(
            ProviderSetupInfo(
                name=name,
                type=ptype,
                base_url=base_url,
                api_key_env=api_key_env,
                api_key=api_key,
                timeout_seconds=120.0,
            )
        )

    # Step 2: Fetch models from all configured providers
    ui.text("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    ui.text("[bold]Step 2: Model Discovery[/bold] — Fetching models from all providers...")
    ui.text("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    all_models: list[tuple[str, str]] = []  # (provider_name, model_id)

    for cp in configured_providers:
        eff_url = cp.base_url or ("https://api.groq.com/openai/v1" if cp.type == "groq" else "")
        if eff_url:
            ui.text(f"Querying models from {cp.name} ({eff_url})...")
            models = _fetch_models(eff_url, cp.api_key)
            if models:
                ui.ok(f"✓ Found {len(models)} models from {cp.name}")
                for m in models:
                    all_models.append((cp.name, m))
            else:
                ui.warn(f"Could not automatically fetch models from {cp.name}")

    if all_models:
        table = Table(title="Available Models Catalog (All Providers)", show_header=True, header_style="bold cyan", border_style="dim")
        table.add_column("#", style="dim", width=5)
        table.add_column("Provider", style="magenta", width=14)
        table.add_column("Model ID", style="green")
        for i, (p_name, m_id) in enumerate(all_models, 1):
            table.add_row(str(i), p_name, m_id)
        console.print(table)
    else:
        ui.warn("No online models could be discovered automatically. You can specify model names manually.")

    # Step 3: Sequential agent model selection
    ui.text("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    ui.text("[bold]Step 3: Agent Model Selection[/bold] — Select model for each agent role in sequence")
    ui.text("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    def _resolve_selection(role_label: str, default_val: tuple[str, str] | None) -> tuple[str, str]:
        fallback_default = "llama-3.3-70b-versatile" if (configured_providers and configured_providers[0].type == "groq") else "gpt-4o-mini"
        def_prompt = "1" if all_models else fallback_default
        if default_val:
            if default_val in all_models:
                def_prompt = str(all_models.index(default_val) + 1)
            else:
                def_prompt = default_val[1]

        prompt_str = f"Select model for {role_label}"
        if all_models:
            prompt_str += f" (enter # 1-{len(all_models)} or type name)"
        else:
            prompt_str += " (type model name)"

        user_input = Prompt.ask(prompt_str, default=def_prompt).strip()
        user_input = _strip_quotes(user_input)

        if all_models:
            try:
                num = int(user_input)
                if 1 <= num <= len(all_models):
                    chosen = all_models[num - 1]
                    ui.ok(f"✓ {role_label}: [{chosen[0]}] {chosen[1]}")
                    return chosen
            except ValueError:
                pass

            # Check if typed model matches any known model
            for p, m in all_models:
                if m.lower() == user_input.lower():
                    ui.ok(f"✓ {role_label}: [{p}] {m}")
                    return (p, m)

        # Fallback to first provider
        fallback_prov = configured_providers[0].name
        ui.ok(f"✓ {role_label}: [{fallback_prov}] {user_input}")
        return (fallback_prov, user_input)

    # 1. Architect
    architect_choice = _resolve_selection("Architect (planning & architecture)", all_models[0] if all_models else None)

    # 2. Builder
    builder_choice = _resolve_selection("Builder (code generation & tools)", architect_choice)

    # 3. Supervisor
    supervisor_choice = _resolve_selection("Supervisor (verification & review)", architect_choice)

    # 4. Expert Coder
    expert_choice = _resolve_selection("Expert Coder (deep debugging & algorithms)", builder_choice)

    role_bindings = {
        "architect": architect_choice,
        "builder": builder_choice,
        "supervisor": supervisor_choice,
        "expert_coder": expert_choice,
    }

    # Step 4: Sandbox & Approval Mode
    ui.text("\n[bold]Step 4: Permissions & Sandbox[/bold]")
    use_sandbox = Confirm.ask("Enable Docker sandbox for command execution?", default=False)
    mode = Prompt.ask("Approval mode for commands and network", choices=["auto", "ask", "safe"], default="ask")

    answers = SetupAnswers(
        providers=configured_providers,
        role_bindings=role_bindings,
        sandbox_enabled=use_sandbox,
        approval_mode=mode,
    )

    apply_setup(answers, global_dir=g_dir)
    ui.ok(f"\n✓ Setup complete! Configuration successfully written to {g_dir}")

