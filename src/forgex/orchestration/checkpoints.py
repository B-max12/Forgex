"""Git checkpoint system (spec section 21).

rollback_to: create a SAFETY checkpoint of the current state FIRST, then
git reset --hard to the target commit — so every rollback is itself
reversible.
"""

from __future__ import annotations

import logging
import uuid

from forgex.orchestration.stores import ProjectStores
from forgex.schemas.checkpoint import CheckpointRecord
from forgex.schemas.error import GitError
from forgex.schemas.event import EventType
from forgex.tools.git import git_checkpoint, git_reset_hard, has_git_repo

logger = logging.getLogger("forgex.checkpoints")


def _project_id(stores: ProjectStores) -> str:
    state = stores.state.load()
    return state.project_id if state else "unknown"


def create_checkpoint(
    label: str,
    *,
    stores: ProjectStores,
    description: str | None = None,
    run_id: str | None = None,
) -> CheckpointRecord | None:
    """Commit current state and record it. Returns None when git is unavailable."""
    if not has_git_repo(stores.root):
        return None
    commit = git_checkpoint(stores.root, label)
    if commit is None:
        logger.warning("checkpoint %r: git commit failed", label)
        return None
    record = CheckpointRecord(
        id=uuid.uuid4().hex[:12],
        project_id=_project_id(stores),
        label=label,
        git_commit=commit,
        description=description,
        run_id=run_id,
    )
    if stores.checkpoints is not None:
        stores.checkpoints.insert(record)
    stores.recorder.record(
        EventType.CHECKPOINT_CREATED,
        {"id": record.id, "label": label, "commit": commit},
        run_id=run_id,
    )
    return record


def get_checkpoint(checkpoint_id: str, *, stores: ProjectStores) -> CheckpointRecord | None:
    if stores.checkpoints is None:
        return None
    return stores.checkpoints.get(checkpoint_id)


def latest_checkpoint(*, stores: ProjectStores) -> CheckpointRecord | None:
    if stores.checkpoints is None:
        return None
    return stores.checkpoints.latest(_project_id(stores))


def list_checkpoints(*, stores: ProjectStores, limit: int = 20) -> list[CheckpointRecord]:
    if stores.checkpoints is None:
        return []
    return stores.checkpoints.list(_project_id(stores), limit)


def find_pre_task_checkpoint(task_id: str, *, stores: ProjectStores) -> CheckpointRecord | None:
    target_label = f"pre-{task_id}"
    for cp in list_checkpoints(stores=stores, limit=100):
        if cp.label == target_label:
            return cp
    return None


def rollback_to(
    record: CheckpointRecord,
    *,
    stores: ProjectStores,
    run_id: str | None = None,
) -> CheckpointRecord | None:
    if not record.git_commit:
        raise GitError(f"Checkpoint {record.id} has no git commit hash")

    # 1. Safety checkpoint of current state
    safety = create_checkpoint(
        f"pre-rollback-{record.id}",
        stores=stores,
        description=f"Safety checkpoint before rollback to {record.id}",
        run_id=run_id,
    )

    # 2. Reset hard
    ok = git_reset_hard(stores.root, record.git_commit)
    if not ok:
        raise GitError(f"Failed to reset workspace to commit {record.git_commit}")

    # 3. Record event
    stores.recorder.record(
        EventType.CHECKPOINT_ROLLED_BACK,
        {
            "to": record.id,
            "commit": record.git_commit,
            "safety_checkpoint": safety.id if safety else None,
        },
        run_id=run_id,
    )
    return safety
