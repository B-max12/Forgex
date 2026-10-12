"""inspect_dependencies tool (spec section 49) — language-agnostic manifest parsing."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any

from forgex.sandbox.permissions import Permission
from forgex.tools.base import SimpleTool, Tool, ToolCall, ToolContext, ToolResult


def _dep(name: str, spec: Any, *, dev: bool, source: str) -> dict[str, Any]:
    return {
        "name": name,
        "spec": spec if isinstance(spec, str) and spec else None,
        "dev": dev,
        "source": source,
    }


def _python_deps(root: Path) -> list[dict[str, Any]]:
    deps: list[dict[str, Any]] = []

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            with pyproject.open("rb") as fh:
                data = tomllib.load(fh)
            project = data.get("project") or {}
            for entry in project.get("dependencies") or []:
                name = re.split(r"[=<>!~^ ;\[]", str(entry), maxsplit=1)[0]
                deps.append(_dep(name, str(entry), dev=False, source="pyproject.toml"))
            for group, items in (project.get("optional-dependencies") or {}).items():
                for entry in items:
                    name = re.split(r"[=<>!~^ ;\[]", str(entry), maxsplit=1)[0]
                    deps.append(_dep(name, str(entry), dev=(group == "dev"), source="pyproject.toml"))
        except (OSError, tomllib.TOMLDecodeError):
            pass

    reqs = root / "requirements.txt"
    if reqs.is_file():
        try:
            for line in reqs.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                name = re.split(r"[=<>!~^ ;]", line, maxsplit=1)[0]
                deps.append(_dep(name, line, dev=False, source="requirements.txt"))
        except OSError:
            pass

    return deps


def _node_deps(root: Path) -> list[dict[str, Any]]:
    deps: list[dict[str, Any]] = []
    pkg = root / "package.json"
    if pkg.is_file():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
            for name, spec in (data.get("dependencies") or {}).items():
                deps.append(_dep(name, str(spec), dev=False, source="package.json"))
            for name, spec in (data.get("devDependencies") or {}).items():
                deps.append(_dep(name, str(spec), dev=True, source="package.json"))
        except (OSError, json.JSONDecodeError):
            pass
    return deps


def _cargo_deps(root: Path) -> list[dict[str, Any]]:
    deps: list[dict[str, Any]] = []
    cargo = root / "Cargo.toml"
    if cargo.is_file():
        try:
            with cargo.open("rb") as fh:
                data = tomllib.load(fh)
            for name, spec in (data.get("dependencies") or {}).items():
                deps.append(_dep(name, str(spec), dev=False, source="Cargo.toml"))
            for name, spec in (data.get("dev-dependencies") or {}).items():
                deps.append(_dep(name, str(spec), dev=True, source="Cargo.toml"))
        except (OSError, tomllib.TOMLDecodeError):
            pass
    return deps


def _go_deps(root: Path) -> list[dict[str, Any]]:
    deps: list[dict[str, Any]] = []
    mod = root / "go.mod"
    if mod.is_file():
        try:
            content = mod.read_text(encoding="utf-8", errors="replace")
            in_require = False
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("require ("):
                    in_require = True
                    continue
                if in_require and line == ")":
                    in_require = False
                    continue
                if in_require or line.startswith("require "):
                    if line.startswith("require "):
                        line = line[8:].strip()
                    parts = line.split()
                    if len(parts) >= 2:
                        deps.append(_dep(parts[0], parts[1], dev=False, source="go.mod"))
        except OSError:
            pass
    return deps


async def _inspect_dependencies(call: ToolCall, ctx: ToolContext) -> ToolResult:
    root = ctx.workspace
    all_deps: list[dict[str, Any]] = []
    all_deps.extend(_python_deps(root))
    all_deps.extend(_node_deps(root))
    all_deps.extend(_cargo_deps(root))
    all_deps.extend(_go_deps(root))

    lines = [f"{d['name']} ({d['spec'] or 'any'}) [source: {d['source']}{', dev' if d['dev'] else ''}]" for d in all_deps]
    output = "\n".join(lines) if lines else "(no dependencies declared)"
    return ToolResult(ok=True, output=output, data={"dependencies": all_deps})


def create_tools() -> list[Tool]:
    return [
        SimpleTool(
            name="inspect_dependencies",
            handler=_inspect_dependencies,
            permissions={Permission.READ},
            description="Inspect declared project dependencies across pyproject, package.json, Cargo.toml, go.mod.",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
        )
    ]
