from __future__ import annotations

import pytest

from forgex.orchestration.state import StateStore, TaskStore
from forgex.schemas.error import ProjectError
from forgex.schemas.project import ProjectState
from forgex.schemas.task import Task, TaskPriority


def test_state_roundtrip(tmp_path):
    store = StateStore(tmp_path)
    state = ProjectState(project_id="abc123", project_path=str(tmp_path), user_request="todo api")
    state.changed_files.append("src/main.py")
    store.save(state)
    loaded = store.load()
    assert loaded is not None
    assert loaded.project_id == "abc123"
    assert loaded.user_request == "todo api"
    assert loaded.changed_files == ["src/main.py"]


def test_save_bumps_updated_at(tmp_path):
    store = StateStore(tmp_path)
    state = ProjectState(project_id="x", project_path=str(tmp_path))
    before = state.updated_at
    store.save(state)
    assert state.updated_at >= before
    assert store.load().updated_at == state.updated_at


def test_load_missing_returns_none(tmp_path):
    assert StateStore(tmp_path).load() is None


def test_atomic_write_leaves_no_tmp(tmp_path):
    StateStore(tmp_path).save(ProjectState(project_id="x", project_path=str(tmp_path)))
    assert (tmp_path / ".forgex" / "state.json").is_file()
    assert not list((tmp_path / ".forgex").glob("*.tmp"))


def test_corrupt_state_raises_project_error(tmp_path):
    fx = tmp_path / ".forgex"
    fx.mkdir()
    (fx / "state.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ProjectError):
        StateStore(tmp_path).load()


def test_tasks_roundtrip(tmp_path):
    store = TaskStore(tmp_path)
    assert store.load() == []
    tasks = [
        Task(id="TASK-001", description="Scaffold API", priority=TaskPriority.HIGH),
        Task(id="TASK-002", description="Add tests", depends_on=["TASK-001"],
             acceptance_criteria=["pytest passes"]),
    ]
    store.save(tasks)
    loaded = store.load()
    assert loaded == tasks
    assert loaded[1].depends_on == ["TASK-001"]
    assert loaded[1].acceptance_criteria == ["pytest passes"]


def test_corrupt_tasks_raises_project_error(tmp_path):
    fx = tmp_path / ".forgex"
    fx.mkdir()
    (fx / "tasks.json").write_text("[]", encoding="utf-8")  # wrong shape
    with pytest.raises(ProjectError):
        TaskStore(tmp_path).load()
