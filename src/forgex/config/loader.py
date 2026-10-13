"""Layered configuration loading, saving, and dotted-key editing."""

from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path
from typing import Any

import tomli_w
from pydantic import ValidationError

from forgex.config.schema import ForgexConfig
from forgex.schemas.error import ConfigError

FORGEX_DIR_NAME = ".forgex"
CONFIG_FILE_NAME = "config.toml"
ENV_FILE_NAME = ".env"


def global_config_path() -> Path:
    return Path.home() / FORGEX_DIR_NAME / CONFIG_FILE_NAME


def project_config_path(project_root: Path) -> Path:
    return project_root / FORGEX_DIR_NAME / CONFIG_FILE_NAME


def _read_toml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        msg = f"Invalid TOML in {path}: {exc}"
        raise ConfigError(msg) from exc


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(
    project_root: Path | None = None,
    overrides: dict[str, Any] | None = None,
) -> ForgexConfig:
    """Load merged configuration: defaults < global < project < overrides."""
    load_env_files(project_root)
    data: dict[str, Any] = ForgexConfig().model_dump()
    data = _deep_merge(data, _read_toml(global_config_path()))
    if project_root is not None:
        data = _deep_merge(data, _read_toml(project_config_path(project_root)))
    if overrides:
        data = _deep_merge(data, overrides)
    try:
        config = ForgexConfig.model_validate(data)
    except ValidationError as exc:
        msg = f"Invalid configuration: {exc.error_count()} error(s): {exc}"
        raise ConfigError(msg) from exc

    if os.environ.get("FORGEX_OFFLINE") == "1":
        # Offline mode (§73): web research off; local providers still allowed.
        config.research.enabled = False
    return config


def save_config(config: ForgexConfig, path: Path) -> None:
    """Write a full config to *path* as TOML (None values omitted — TOML has no null)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = tomli_w.dumps(config.model_dump(mode="json", exclude_none=True))
    path.write_text(text, encoding="utf-8")


def _coerce(raw: Any) -> Any:
    """Convert a CLI string into bool/int/float/JSON when unambiguous."""
    if not isinstance(raw, str):
        return raw
    if raw.lower() in ("true", "false"):
        return raw.lower() == "true"
    if raw and raw[0] in "[{":
        try:
            return json.loads(raw)
        except ValueError:
            pass
    for cast in (int, float):
        try:
            return cast(raw)
        except ValueError:
            pass
    return raw


def set_config_value(path: Path, dotted_key: str, value: Any) -> ForgexConfig:
    """Set a dotted key in config at path, validate with Pydantic, and save.

    Refuses to write if the resulting configuration would be invalid.
    """
    raw_dict = _read_toml(path) if path.is_file() else {}
    coerced_value = _coerce(value)

    # Insert into nested dict
    parts = dotted_key.split(".")
    curr = raw_dict
    for part in parts[:-1]:
        if part not in curr or not isinstance(curr[part], dict):
            curr[part] = {}
        curr = curr[part]
    curr[parts[-1]] = coerced_value

    # Merge onto defaults to validate full schema
    data = ForgexConfig().model_dump()
    data = _deep_merge(data, raw_dict)

    try:
        validated = ForgexConfig.model_validate(data)
    except ValidationError as exc:
        msg = f"Invalid configuration for {dotted_key}={value}: {exc}"
        raise ConfigError(msg) from exc

    # Write validated TOML
    path.parent.mkdir(parents=True, exist_ok=True)
    # Save the minimal raw_dict or full validated config
    save_config(validated, path)
    return validated


def parse_env_file(path: Path) -> dict[str, str]:
    """Minimal .env parser: comments, optional 'export ', KEY=VALUE, quotes."""
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        line = line.removeprefix("export ")
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def load_env_files(project_root: Path | None = None) -> list[Path]:
    """Load ~/.forgex/.env then <project>/.env into os.environ with setdefault.

    Priority: real environment always wins; project .env beats global .env.
    """
    paths = []
    if project_root is not None:
        paths.append(Path(project_root) / ENV_FILE_NAME)
    paths.append(Path.home() / FORGEX_DIR_NAME / ENV_FILE_NAME)
    loaded: list[Path] = []
    for path in paths:
        if not path.is_file():
            continue
        try:
            values = parse_env_file(path)
        except OSError:
            continue
        for key, value in values.items():
            if not os.environ.get(key):
                os.environ[key] = value
        loaded.append(path)
    return loaded


def store_secret(env_var: str, value: str, *, global_dir: Path | None = None) -> Path:
    """Persist a secret to ~/.forgex/.env (chmod 600). Never into config files."""
    target = (global_dir or Path.home() / FORGEX_DIR_NAME) / ENV_FILE_NAME
    target.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, str] = parse_env_file(target) if target.is_file() else {}
    existing[env_var] = value
    lines = [f"{key}={val}" for key, val in existing.items()]
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if os.name == "posix":
        try:
            os.chmod(target, 0o600)
        except OSError:
            pass
    return target
