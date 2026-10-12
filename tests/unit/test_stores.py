from __future__ import annotations

from datetime import UTC, datetime

from forgex.orchestration.stores import open_stores
from forgex.schemas.error import ErrorRecord
from forgex.schemas.event import EventType
from forgex.schemas.project import ProjectState
from forgex.schemas.task import Task


def test_open_stores_creates_db_and_mirrors(tmp_path):
    fx = tmp_path / ".forgex"
    fx.mkdir()
    with open_stores(tmp_path) as stores:
        assert stores.db is not None
        state = ProjectState(project_id="p1", project_path=str(tmp_path))
        state.errors.append(
            ErrorRecord(ts=datetime.now(UTC), source="builder", kind="ToolError", message="boom")
        )
        stores.save_state(state)
        stores.save_tasks([Task(id="TASK-001", description="x")], project_id="p1")
        stores.recorder.record(EventType.RUN_STARTED, {"request": "demo"}, run_id="r1")

        assert stores.projects.get("p1") is not None
        assert [t.id for t in stores.task_repo.list("p1")] == ["TASK-001"]
        assert stores.events_repo.count() == 1
        assert len(stores.errors.list("p1")) == 1
    # durable JSON is the source of truth
    assert (fx / "state.json").is_file()
    assert (fx / "tasks.json").is_file()
    assert (fx / "events.jsonl").read_text(encoding="utf-8").count("\n") == 1


def test_open_stores_degraded_mode_never_creates_db(tmp_path):
    fx = tmp_path / ".forgex"
    fx.mkdir()
    with open_stores(tmp_path, create_db=False) as stores:
        assert stores.db is None
        assert stores.runs is None
        stores.recorder.record(EventType.PROJECT_INITIALIZED, {})
    assert not (fx / "state.db").exists()
    assert (fx / "events.jsonl").read_text(encoding="utf-8").strip() != ""
