from __future__ import annotations

from pathlib import Path

import pytest

from forgex.orchestration.state import StateStore, TaskStore
from forgex.orchestration.stores import open_stores
from forgex.project import initialize_project
from forgex.schemas.error import ProjectError
from forgex.schemas.project import WorkflowStatus


def test_creates_scaffold_and_state(tmp_path: Path):
    root = initialize_project(tmp_path / "proj")
    fx = root / ".forgex"
    assert (fx / "config.toml").is_file()
    assert (fx / "events.jsonl").is_file()
    assert (fx / "state.json").is_file()
    assert (fx / "tasks.json").is_file()
    assert (fx / "checkpoints").is_dir()
    assert (fx / "cache").is_dir()

    gitignore = (fx / ".gitignore").read_text().splitlines()
    assert "cache/" in gitignore
    assert "state.db" in gitignore

    state = StateStore(root).load()
    assert state is not None
    assert state.status is WorkflowStatus.INITIALIZING
    assert state.project_id
    assert TaskStore(root).load() == []

    lines = (fx / "events.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1 and "ProjectInitialized" in lines[0]


def test_init_records_event_in_db_index(tmp_path: Path):
    root = initialize_project(tmp_path)
    with open_stores(root, create_db=False) as stores:
        assert stores.events_repo is not None
        assert stores.events_repo.count() == 1


def test_refuses_overwrite(tmp_path: Path):
    initialize_project(tmp_path)
    with pytest.raises(ProjectError):
        initialize_project(tmp_path)


def test_rejects_file_target(tmp_path: Path):
    f = tmp_path / "afile"
    f.write_text("x", encoding="utf-8")
