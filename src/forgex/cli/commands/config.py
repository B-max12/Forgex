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
from forgex.models.groq import DEFAULT_API_KEY_ENV as GROQ_KEY_ENV
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
class SetupAnswers:
    provider: str
    base_url: str | None = None
    api_key_env: str | None = None
    api_key: str | None = None
    models: dict[str, str] = field(default_factory=dict)
    sandbox_enabled: bool = False
    approval_mode: str = "ask"


def apply_setup(answers: SetupAnswers, *, global_dir: Path) -> None:
    path = global_dir / CONFIG_FILE_NAME
    if answers.base_url:
        set_config_value(path, f"providers.{answers.provider}.type", "openai_compatible")
        set_config_value(path, f"providers.{answers.provider}.base_url", answers.base_url)
        if answers.api_key_env:
            set_config_value(path, f"providers.{answers.provider}.api_key_env", answers.api_key_env)
    if answers.api_key and answers.api_key_env:
        store_secret(answers.api_key_env, answers.api_key, global_dir=global_dir)

    for role, model in answers.models.items():
        set_config_value(path, f"models.{role}.provider", answers.provider)
        set_config_value(path, f"models.{role}.model", model)

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
        with httpx.Client(timeout=4.0) as client:
            resp = client.get(url, headers=headers)
            if resp.status_code in (200, 201):
                return True, "Connection verified (HTTP 200)"
            return False, f"Provider returned HTTP {resp.status_code}"
    except Exception as exc:
        return False, str(exc)


@app.command("setup")
def setup_command(
    ctx: typer.Context,
) -> None:
    """Interactive setup wizard for provider credentials and defaults."""
    ui = ui_from(ctx)
    ui.text("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    ui.text("FORGEX Configuration Setup Wizard — Welcome!")
    ui.text("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    ui.text("Security & Terms Notice:")
    ui.text(" • FORGEX operates locally and executes developer tools.")
    ui.text(" • Reversible checkpoints are created before file edits.")
    ui.text(" • API keys are stored with restricted permissions (0600) in ~/.forgex/.env.")
    ui.text(" • You control permissions via mode: ask (default), auto, or safe.\n")

    prov = Prompt.ask("Choose provider", choices=["groq", "openai", "local", "custom"], default="groq")

    base_url = None
    api_key_env = "FORGEX_GROQ_API_KEY"
    api_key = None

    if prov == "groq":
        provider_name = "groq"
        api_key = Prompt.ask("Enter your Groq API key (leave empty to skip)", password=True, default="")
        default_model = "llama-3.3-70b-versatile"
    elif prov == "openai":
        provider_name = "openai_compatible"
        api_key_env = "FORGEX_OPENAI_API_KEY"
        api_key = Prompt.ask("Enter your OpenAI API key (leave empty to skip)", password=True, default="")
        default_model = "gpt-4o-mini"
    elif prov == "local":
        provider_name = "local"
        base_url = Prompt.ask("Enter local OpenAI-compatible endpoint", default="http://localhost:11434/v1")
        api_key_env = None
        default_model = Prompt.ask("Enter model name", default="llama3.1:8b")
    else:
        provider_name = Prompt.ask("Enter custom provider name", default="custom")
        base_url = Prompt.ask("Enter base URL", default="http://localhost:8080/v1")
        api_key_env = f"FORGEX_{provider_name.upper()}_API_KEY"
        api_key = Prompt.ask("Enter API key (if required)", password=True, default="")
        default_model = Prompt.ask("Enter default model", default="qwen2.5:14b")

    # Health check verification
    if api_key or (prov == "local" and base_url):
        ui.text(f"Testing connectivity to {provider_name}...")
        ok, detail = _test_provider_connectivity(provider_name, base_url, api_key)
        if ok:
            ui.ok(f"Provider connection verified: {detail}")
        else:
            ui.warn(f"Provider test: {detail} (proceeding; test with `forgex doctor --ping`)")

    models = {
        "architect": default_model,
        "builder": default_model,
        "expert_coder": default_model,
        "supervisor": default_model,
    }

    if Confirm.ask("Customize models for specific agent roles?", default=False):
        for role in ("architect", "builder", "expert_coder", "supervisor"):
            models[role] = Prompt.ask(f"Model for {role}", default=default_model)

    use_sandbox = Confirm.ask("Enable Docker sandbox for command execution?", default=False)
    mode = Prompt.ask("Approval mode for commands and network", choices=["auto", "ask", "safe"], default="ask")

    answers = SetupAnswers(
        provider=provider_name,
        base_url=base_url,
        api_key_env=api_key_env,
        api_key=api_key or None,
        models=models,
        sandbox_enabled=use_sandbox,
        approval_mode=mode,
    )

    g_dir = global_config_path().parent
    apply_setup(answers, global_dir=g_dir)
    ui.ok(f"Setup complete! Config written to {g_dir}")
