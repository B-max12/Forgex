from __future__ import annotations

from forgex.schemas.checkpoint import CheckpointRecord
from forgex.schemas.project import ProjectState, WorkflowStatus
from forgex.schemas.result import ModelUsageRecord
from forgex.storage.database import Database
from forgex.storage.migrations import run_migrations
from forgex.storage.repositories import (
    CheckpointRepository,
    ModelUsageRepository,
    ProjectRepository,
)

EXPECTED_TABLES = {
    "projects", "runs", "tasks", "events", "errors", "model_usage", "checkpoints"
}


def _project(tmp_path) -> ProjectState:
    return ProjectState(
        project_id="p1",
        project_path=str(tmp_path / "proj"),
        status=WorkflowStatus.PLANNING,
    )


def test_migrations_create_tables(tmp_path):
    db = Database(tmp_path / "state.db")
    names = {
        r["name"] for r in db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert EXPECTED_TABLES <= names
    db.close()


def test_migrations_idempotent(tmp_path):
    db = Database(tmp_path / "state.db")
    assert run_migrations(db.conn) == 3
    db.close()


def test_project_upsert(tmp_path):
    db = Database(tmp_path / "state.db")
    repo = ProjectRepository(db)
    state = _project(tmp_path)
    repo.upsert(state)
    state.status = WorkflowStatus.BUILDING
    repo.upsert(state)
    loaded = repo.get("p1")
    assert loaded is not None and loaded.status == WorkflowStatus.BUILDING
    db.close()


def test_model_usage_repository(tmp_path):
    db = Database(tmp_path / "state.db")
    repo = ModelUsageRepository(db)
    repo.insert(ModelUsageRecord(run_id="r1", agent="architect", provider="groq",
                                 model="llama-3.3-70b-versatile", input_tokens=100,
                                 output_tokens=20, total_tokens=120, latency_ms=123.4))
    repo.insert(ModelUsageRecord(agent="builder", provider="groq", model="m",
                                 latency_ms=10.0, success=False, error="RateLimitError"))
    rows = repo.recent()
    assert len(rows) == 2
    assert rows[0].success is False and rows[0].error == "RateLimitError"
    db.close()


def test_checkpoint_repository(tmp_path):
    db = Database(tmp_path / "state.db")
    repo = CheckpointRepository(db)
    repo.insert(CheckpointRecord(id="cp1", project_id="p1", label="first",
                                 git_commit="abc123"))
    repo.insert(CheckpointRecord(id="cp2", project_id="p1", label="second",
                                 git_commit="def456"))
    assert repo.get("cp1").label == "first"
    assert repo.latest("p1").id == "cp2"
    assert [r.id for r in repo.list("p1")] == ["cp2", "cp1"]
    db.close()
