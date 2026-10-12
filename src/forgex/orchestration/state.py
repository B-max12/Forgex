"""Durable project state persistence (spec sections 5, 6, 36).

JSON files under .forgex/ are the canonical, human-inspectable,
git-friendly source of truth. Writes are atomic (tmp + fsync + rename)
so an interrupt can never corrupt state (spec section 36).
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from forgex.schemas.error import ProjectError
from forgex.schemas.project import ProjectState
from forgex.schemas.task import Task

STATE_FILE = "state.json"
TASKS_FILE = "tasks.json"


def _atomic_write_json(path: Path, payload: Any) -> None:
    """Write JSON atomically: temp file, fsync, rename (spec section 36)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


class StateStore:
    """Reads/writes .forgex/state.json."""

    def __init__(self, project_root: str | Path) -> None:
        self._dir = Path(project_root) / ".forgex"

    def path(self) -> Path:
        return self._dir / STATE_FILE

    def load(self) -> ProjectState | None:
        """Load state; None when no state file exists yet.

        Raises ProjectError if the file is corrupt.
        """
        state_path = self.path()
        if not state_path.is_file():
            return None
        try:
            content = state_path.read_text(encoding="utf-8")
            data = json.loads(content)
            return ProjectState.model_validate(data)
        except (json.JSONDecodeError, ValidationError, UnicodeDecodeError) as exc:
            raise ProjectError(f"Corrupt state file {state_path}: {exc}") from exc

    def save(self, state: ProjectState) -> None:
        state.updated_at = datetime.now(UTC)
        _atomic_write_json(self.path(), state.model_dump(mode="json"))


class TaskStore:
    """Reads/writes .forgex/tasks.json."""

    def __init__(self, project_root: str | Path) -> None:
        self._dir = Path(project_root) / ".forgex"

    def path(self) -> Path:
        return self._dir / TASKS_FILE

    def load(self) -> list[Task]:
        task_path = self.path()
        if not task_path.is_file():
            return []
        try:
            content = task_path.read_text(encoding="utf-8")
            data = json.loads(content)
            if not isinstance(data, dict) or "tasks" not in data or not isinstance(data["tasks"], list):
                raise ProjectError(f"Expected a dict with 'tasks' list in {task_path}")
            return [Task.model_validate(item) for item in data["tasks"]]
        except (json.JSONDecodeError, ValidationError, UnicodeDecodeError, ProjectError) as exc:
            raise ProjectError(f"Corrupt tasks file {task_path}: {exc}") from exc

    def save(self, tasks: list[Task]) -> None:
        _atomic_write_json(self.path(), {"tasks": [t.model_dump(mode="json") for t in tasks]})
