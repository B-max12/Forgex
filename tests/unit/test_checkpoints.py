import subprocess
from pathlib import Path

import pytest

from forgex.orchestration.checkpoints import (
    create_checkpoint, list_checkpoints, rollback_to,
)
from forgex.orchestration.events import read_events
from forgex.orchestration.stores import open_stores
from forgex.schemas.checkpoint import CheckpointRecord
from forgex.schemas.error import GitError
from forgex.schemas.event import EventType
from forgex.tools.git import git_checkpoint


def git_repo(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir(exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True, capture_output=True)
    return tmp_path


def test_create_checkpoint_persists_metadata_and_event(tmp_path, monkeypatch):
    git_repo(tmp_path, monkeypatch)
    (tmp_path / "a.txt").write_text("v1", encoding="utf-8")
    with open_stores(tmp_path) as stores:
        record = create_checkpoint("first", stores=stores)
        assert record is not None and record.git_commit
        assert record.git_commit in subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=tmp_path,
            capture_output=True, text=True, check=True).stdout
        assert stores.checkpoints.get(record.id) is not None
        events = read_events(tmp_path / ".forgex" / "events.jsonl",
                             event_type=EventType.CHECKPOINT_CREATED)
        assert events and events[-1].data["id"] == record.id


def test_create_without_git_returns_none(tmp_path):
    with open_stores(tmp_path) as stores:
        assert create_checkpoint("x", stores=stores) is None


def test_list_newest_first(tmp_path, monkeypatch):
    git_repo(tmp_path, monkeypatch)
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    with open_stores(tmp_path) as stores:
        first = create_checkpoint("first", stores=stores)
        (tmp_path / "b.txt").write_text("x", encoding="utf-8")
        second = create_checkpoint("second", stores=stores)
        listed = list_checkpoints(stores=stores)
        assert [r.id for r in listed][:2] == [second.id, first.id]


def test_rollback_restores_state_and_creates_safety(tmp_path, monkeypatch):
    git_repo(tmp_path, monkeypatch)
    (tmp_path / "a.txt").write_text("v1", encoding="utf-8")
    with open_stores(tmp_path) as stores:
        cp1 = create_checkpoint("cp1", stores=stores)
        (tmp_path / "a.txt").write_text("v2", encoding="utf-8")
        (tmp_path / "new.txt").write_text("uncommitted", encoding="utf-8")
        cp2 = create_checkpoint("cp2", stores=stores)

        safety = rollback_to(cp1, stores=stores)

        assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "v1"
        assert safety is not None  # current state (v2 + new.txt) preserved
        events = read_events(tmp_path / ".forgex" / "events.jsonl",
                             event_type=EventType.CHECKPOINT_ROLLED_BACK)
        assert events and events[-1].data["to"] == cp1.id

        # rollback of the rollback restores everything
        rollback_to(safety, stores=stores)
        assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "v2"
        assert (tmp_path / "new.txt").exists()


def test_rollback_without_commit_raises(tmp_path, monkeypatch):
    git_repo(tmp_path, monkeypatch)
    with open_stores(tmp_path) as stores:
        state = stores.state.load()
        proj_id = state.project_id if state else "proj-test"
        record = CheckpointRecord(id="cp-x", project_id=proj_id,
                                  label="broken", git_commit=None)
        with pytest.raises(GitError):
            rollback_to(record, stores=stores)
