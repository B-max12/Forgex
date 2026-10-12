"""Project services: detection and initialization.

The CLI stays thin; future hosts (FastAPI server, web UI) call these
functions directly (spec section 60).
"""

from __future__ import annotations

import json
import tomllib
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from forgex.schemas.error import ProjectError
from forgex.schemas.event import EventType
from forgex.schemas.project import ProjectState, WorkflowStatus

FORGEX_DIR = ".forgex"

_PROJECT_CONFIG_TEMPLATE = """\
# FORGEX project configuration.
# Values here override ~/.forgex/config.toml — see `forgex config show`.

[workflow]
max_iterations = 5

[permissions]
mode = "ask"
"""


@dataclass
class ProjectDetection:
    root: Path
    languages: list[str] = field(default_factory=list)
    package_managers: list[str] = field(default_factory=list)
    build_systems: list[str] = field(default_factory=list)
    test_frameworks: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    has_git: bool = False

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["root"] = str(self.root)
        return d

    def summary(self) -> str:
        parts: list[str] = []
        if self.languages:
            parts.append(f"Languages: {', '.join(self.languages)}")
        if self.frameworks:
            parts.append(f"Frameworks: {', '.join(self.frameworks)}")
        if self.test_frameworks:
            parts.append(f"Tests: {', '.join(self.test_frameworks)}")
        if self.package_managers:
            parts.append(f"Packages: {', '.join(self.package_managers)}")
        return " | ".join(parts) if parts else "Empty / undetected project"


def detect_project(root: Path) -> ProjectDetection:
    root = Path(root).resolve()
    det = ProjectDetection(root=root)

    # Git
    det.has_git = (root / ".git").exists()

    # Python
    pyproject = root / "pyproject.toml"
    requirements = root / "requirements.txt"
    setup_py = root / "setup.py"
    if pyproject.is_file() or requirements.is_file() or setup_py.is_file() or list(root.glob("*.py")) or (root / "src").is_dir():
        if "Python" not in det.languages:
            det.languages.append("Python")

    py_deps: list[str] = []
    if pyproject.is_file():
        try:
            with pyproject.open("rb") as fh:
                data = tomllib.load(fh)
                project = data.get("project") or {}
                for dep in project.get("dependencies") or []:
                    py_deps.append(str(dep).lower())
                for grp in (project.get("optional-dependencies") or {}).values():
                    for dep in grp:
                        py_deps.append(str(dep).lower())
                if "tool" in data and "poetry" in data["tool"]:
                    if "poetry" not in det.package_managers:
                        det.package_managers.append("poetry")
        except (OSError, tomllib.TOMLDecodeError):
            pass

    if requirements.is_file():
        try:
            for line in requirements.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    py_deps.append(line.lower())
            if "pip" not in det.package_managers:
                det.package_managers.append("pip")
        except OSError:
            pass

    for dep in py_deps:
        if "fastapi" in dep and "FastAPI" not in det.frameworks:
            det.frameworks.append("FastAPI")
        if "flask" in dep and "Flask" not in det.frameworks:
            det.frameworks.append("Flask")
        if "django" in dep and "Django" not in det.frameworks:
            det.frameworks.append("Django")
        if "sqlalchemy" in dep and "SQLAlchemy" not in det.frameworks:
            det.frameworks.append("SQLAlchemy")
        if "pytest" in dep and "Pytest" not in det.test_frameworks:
            det.test_frameworks.append("Pytest")
        if "unittest" in dep and "unittest" not in det.test_frameworks:
            det.test_frameworks.append("unittest")

    # JavaScript / TypeScript / Node
    pkg_json = root / "package.json"
    if pkg_json.is_file():
        if "JavaScript" not in det.languages:
            det.languages.append("JavaScript")
        if "npm" not in det.package_managers:
            det.package_managers.append("npm")
        try:
            pkg_data = json.loads(pkg_json.read_text(encoding="utf-8"))
            deps = dict(pkg_data.get("dependencies") or {})
            deps.update(pkg_data.get("devDependencies") or {})
            for d in deps:
                d_lower = d.lower()
                if "typescript" in d_lower and "TypeScript" not in det.languages:
                    det.languages.append("TypeScript")
                if "express" in d_lower and "Express" not in det.frameworks:
                    det.frameworks.append("Express")
                if "react" in d_lower and "React" not in det.frameworks:
                    det.frameworks.append("React")
                if "next" in d_lower and "Next.js" not in det.frameworks:
                    det.frameworks.append("Next.js")
                if ("jest" in d_lower or "vitest" in d_lower) and "Jest" not in det.test_frameworks:
                    det.test_frameworks.append("Jest")
        except (OSError, json.JSONDecodeError):
            pass

    if (root / "pnpm-lock.yaml").is_file():
        if "pnpm" not in det.package_managers:
            det.package_managers.append("pnpm")
    if (root / "yarn.lock").is_file():
        if "yarn" not in det.package_managers:
            det.package_managers.append("yarn")

    # Rust
    if (root / "Cargo.toml").is_file():
        if "Rust" not in det.languages:
            det.languages.append("Rust")
        if "cargo" not in det.package_managers:
            det.package_managers.append("cargo")

    # Go
    if (root / "go.mod").is_file():
        if "Go" not in det.languages:
            det.languages.append("Go")
        if "go" not in det.package_managers:
            det.package_managers.append("go")

    return det


def initialize_project(target: Path) -> Path:
    target = Path(target).resolve()
    if target.is_file():
        raise ProjectError(f"Target path {target} is a file, not a directory")

    target.mkdir(parents=True, exist_ok=True)
    forgex_dir = target / FORGEX_DIR
    if forgex_dir.is_dir():
        raise ProjectError(f"Project already initialized at {target}")

    forgex_dir.mkdir(parents=True, exist_ok=True)
    (forgex_dir / "checkpoints").mkdir(exist_ok=True)
    (forgex_dir / "cache").mkdir(exist_ok=True)

    # Scaffolding files
    (forgex_dir / "config.toml").write_text(_PROJECT_CONFIG_TEMPLATE, encoding="utf-8")
    (forgex_dir / ".gitignore").write_text("cache/\nstate.db\nstate.db-wal\nstate.db-shm\nrun.lock\n", encoding="utf-8")

    # Project state
    project_id = uuid.uuid4().hex[:12]
    now = datetime.now(UTC)
    state = ProjectState(
        project_id=project_id,
        project_path=str(target),
        created_at=now,
        updated_at=now,
        status=WorkflowStatus.INITIALIZING,
    )

    from forgex.orchestration.stores import open_stores

    with open_stores(target, create_db=True) as stores:
        stores.save_state(state)
        stores.save_tasks([], project_id=project_id)
        stores.recorder.record(
            EventType.PROJECT_INITIALIZED,
            {"project_id": project_id, "root": str(target)},
        )

    return target
