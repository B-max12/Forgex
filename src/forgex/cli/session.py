"""Interactive session state management for FORGEX REPL."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.console import Console

from forgex.cli.context_memory import ConversationContext
from forgex.cli.ui import UI, Output
from forgex.config import ForgexConfig, load_config
from forgex.config.loader import load_env_files
from forgex.orchestration.state import StateStore, TaskStore
from forgex.project import ProjectDetection, detect_project
from forgex.schemas.project import ProjectState
from forgex.schemas.task import Task
from forgex.utils.paths import find_project_root


@dataclass
class Session:
    """Encapsulates persistent state during an interactive FORGEX terminal session."""

    project_root: Path | None = None
    config: ForgexConfig = field(default_factory=ForgexConfig)
    ui: UI = field(default_factory=lambda: UI(mode=Output.RICH))
    console: Console = field(default_factory=Console)
    history: list[str] = field(default_factory=list)
    context: ConversationContext = field(default_factory=ConversationContext)
    _router: Any = None

    def __post_init__(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        """Refresh project root, environment, and configuration from disk."""
        self.project_root = find_project_root()
        load_env_files(self.project_root)
        self.config = load_config(self.project_root)
        self._router = None

    @property
    def is_attached(self) -> bool:
        """True if the session is currently attached to an initialized project."""
        return self.project_root is not None and (self.project_root / ".forgex").is_dir()

    @property
    def project_name(self) -> str:
        """Name of the attached project directory, or 'unattached'."""
        if self.project_root is not None:
            return self.project_root.name
        return "unattached"

    def detect(self) -> ProjectDetection | None:
        """Run project detector on current directory or attached project."""
        target = self.project_root or Path.cwd()
        return detect_project(target)

    def get_state(self) -> ProjectState | None:
        """Load current ProjectState if attached."""
        if not self.is_attached or self.project_root is None:
            return None
        try:
            return StateStore(self.project_root).load()
        except Exception:
            return None

    def get_tasks(self) -> list[Task]:
        """Load project tasks if attached."""
        if not self.is_attached or self.project_root is None:
            return []
        try:
            return TaskStore(self.project_root).load()
        except Exception:
            return []

    def get_router(self) -> Any:
        """Lazily instantiate and return the ModelRouter."""
        if self._router is None:
            from forgex.models.router import ModelRouter

            self._router = ModelRouter(self.config)
        return self._router

    def change_directory(self, target: Path | str) -> bool:
        """Change working directory and refresh session."""
        dest = Path(target).expanduser().resolve()
        if not dest.is_dir():
            return False
        os.chdir(dest)
        self.refresh()
        return True
