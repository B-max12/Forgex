"""Project persistence bundle — the dependency-injection point.

`open_stores()` gives every service a single handle to all durable storage
for one project:
  * StateStore / TaskStore — canonical JSON files in .forgex/
  * EventRecorder          — durable events.jsonl + SQLite index
  * repositories           — SQLite query index + run history

JSON files are the source of truth; the SQLite index is rebuildable.
With `create_db=False` the stores run in degraded JSON-only mode and
never create a database (used by read-only commands like `status`).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from forgex.orchestration.events import EventRecorder
from forgex.orchestration.state import StateStore, TaskStore
from forgex.schemas.project import ProjectState
from forgex.schemas.task import Task
from forgex.storage.database import Database
from forgex.storage.repositories import (
    CheckpointRepository,
    ErrorRepository,
    EventRepository,
    ModelUsageRepository,
    ProjectRepository,
    RunRepository,
    TaskRepository,
)

DB_FILE_NAME = "state.db"


class ProjectStores:
    """All persistence handles for one project."""

    def __init__(self, project_root: str | Path, db: Database | None) -> None:
        self.root = Path(project_root)
        self.forgex_dir = self.root / ".forgex"
        self.db = db
        self.state = StateStore(self.root)
        self.tasks = TaskStore(self.root)
        self.projects = ProjectRepository(db) if db else None
        self.runs = RunRepository(db) if db else None
        self.task_repo = TaskRepository(db) if db else None
        self.events_repo = EventRepository(db) if db else None
        self.errors = ErrorRepository(db) if db else None
        self.usage = ModelUsageRepository(db) if db else None
        self.checkpoints = CheckpointRepository(db) if db else None
        self.recorder = EventRecorder(self.forgex_dir / "events.jsonl", self.events_repo)

    def save_state(self, state: ProjectState) -> None:
        """Canonical save: durable JSON first, then mirror to the SQLite index."""
        self.state.save(state)
        if self.projects is not None:
            self.projects.upsert(state)
        if self.errors is not None and state.errors:
            for err in state.errors:
                self.errors.insert(err, state.project_id)

    def save_tasks(self, tasks: list[Task], project_id: str) -> None:
        """Save tasks: durable JSON first, then mirror to the SQLite index."""
        self.tasks.save(tasks)
        if self.task_repo is not None:
            for task in tasks:
                self.task_repo.upsert(task, project_id)

    def close(self) -> None:
        if self.db is not None:
            self.db.close()


@contextmanager
def open_stores(project_root: str | Path, *, create_db: bool = True) -> Iterator[ProjectStores]:
    root = Path(project_root)
    db_path = root / ".forgex" / DB_FILE_NAME

    db = None
    if create_db or db_path.is_file():
        db = Database(db_path)

    stores = ProjectStores(root, db)
    try:
        yield stores
    finally:
        stores.close()
