"""SQLite repositories (spec section 25).

Pure persistence: parameterized SQL, no business logic, no JSON-file
knowledge. Every sqlite error is wrapped in StorageError so callers only
ever see controlled FORGEX failures (spec section 28).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from forgex.schemas.checkpoint import CheckpointRecord
from forgex.schemas.error import ErrorRecord, StorageError
from forgex.schemas.event import Event, EventType
from forgex.schemas.project import ProjectState, RunState, RunStatus, WorkflowStatus
from forgex.schemas.result import ModelUsageRecord
from forgex.schemas.task import Task, TaskPriority, TaskStatus
from forgex.storage.database import Database


def _iso(value: datetime) -> str:
    return value.isoformat()


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class ProjectRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def upsert(self, state: ProjectState) -> None:
        try:
            self._db.conn.execute(
                """
                INSERT INTO projects (project_id, path, name, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                    path = excluded.path,
                    name = excluded.name,
                    status = excluded.status,
                    updated_at = excluded.updated_at
                """,
                (
                    state.project_id,
                    state.project_path,
                    Path(state.project_path).name,
                    state.status.value,
                    _iso(state.created_at),
                    _iso(state.updated_at),
                ),
            )
            self._db.conn.commit()
        except sqlite3.Error as exc:
            raise StorageError(f"Failed to upsert project: {exc}") from exc

    def get(self, project_id: str) -> ProjectState | None:
        try:
            row = self._db.conn.execute(
                "SELECT * FROM projects WHERE project_id = ?", (project_id,)
            ).fetchone()
            if not row:
                return None
            data = dict(row)
            return ProjectState(
                project_id=data["project_id"],
                project_path=data.get("path") or "",
                status=WorkflowStatus(data["status"]),
                created_at=_dt(data.get("created_at")) or datetime.now(UTC),
                updated_at=_dt(data.get("updated_at")) or datetime.now(UTC),
            )
        except sqlite3.Error as exc:
            raise StorageError(f"Failed to get project: {exc}") from exc


class RunRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def create(self, run: RunState) -> None:
        try:
            self._db.conn.execute(
                """
                INSERT INTO runs (run_id, project_id, request, status, phase, iteration, started_at, finished_at, summary, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.run_id,
                    run.project_id,
                    run.request,
                    run.status.value,
                    run.phase.value,
                    run.iteration,
                    _iso(run.started_at),
                    _iso(run.finished_at) if run.finished_at else None,
                    run.summary,
                    run.error,
                ),
            )
            self._db.conn.commit()
        except sqlite3.Error as exc:
            raise StorageError(f"Failed to create run: {exc}") from exc

    def update(self, run: RunState) -> None:
        try:
            self._db.conn.execute(
                """
                UPDATE runs
                SET status = ?, phase = ?, iteration = ?, finished_at = ?, summary = ?, error = ?
                WHERE run_id = ?
                """,
                (
                    run.status.value,
                    run.phase.value,
                    run.iteration,
                    _iso(run.finished_at) if run.finished_at else None,
                    run.summary,
                    run.error,
                    run.run_id,
                ),
            )
            self._db.conn.commit()
        except sqlite3.Error as exc:
            raise StorageError(f"Failed to update run: {exc}") from exc

    def get(self, run_id: str) -> RunState | None:
        try:
            row = self._db.conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            if not row:
                return None
            return self._to_run(row)
        except sqlite3.Error as exc:
            raise StorageError(f"Failed to get run: {exc}") from exc

    def list_recent(self, project_id: str | None = None, limit: int = 50) -> list[RunState]:
        try:
            if project_id:
                rows = self._db.conn.execute(
                    "SELECT * FROM runs WHERE project_id = ? ORDER BY started_at DESC LIMIT ?",
                    (project_id, limit),
                ).fetchall()
            else:
                rows = self._db.conn.execute(
                    "SELECT * FROM runs ORDER BY started_at DESC LIMIT ?", (limit,)
                ).fetchall()
            return [self._to_run(r) for r in rows]
        except sqlite3.Error as exc:
            raise StorageError(f"Failed to list runs: {exc}") from exc

    @staticmethod
    def _to_run(row: sqlite3.Row) -> RunState:
        return RunState(
            run_id=row["run_id"],
            project_id=row["project_id"],
            request=row["request"],
            status=RunStatus(row["status"]),
            phase=WorkflowStatus(row["phase"]),
            iteration=row["iteration"],
            started_at=_dt(row["started_at"]) or datetime.now(UTC),
            finished_at=_dt(row["finished_at"]),
            summary=row["summary"],
            error=row["error"],
        )


class TaskRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def upsert(self, task: Task, project_id: str) -> None:
        try:
            self._db.conn.execute(
                """
                INSERT INTO tasks (id, project_id, description, priority, status, depends_on, files, acceptance_criteria, attempts, created_at, updated_at, result)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id, project_id) DO UPDATE SET
                    description = excluded.description,
                    priority = excluded.priority,
                    status = excluded.status,
                    depends_on = excluded.depends_on,
                    files = excluded.files,
                    acceptance_criteria = excluded.acceptance_criteria,
                    attempts = excluded.attempts,
                    updated_at = excluded.updated_at,
                    result = excluded.result
                """,
                (
                    task.id,
                    project_id,
                    task.description,
                    task.priority.value,
                    task.status.value,
                    json.dumps(task.depends_on),
                    json.dumps(task.files),
                    json.dumps(task.acceptance_criteria),
                    task.attempts,
                    _iso(task.created_at),
                    _iso(task.updated_at),
                    task.result,
                ),
            )
            self._db.conn.commit()
        except sqlite3.Error as exc:
            raise StorageError(f"Failed to upsert task: {exc}") from exc

    def list(self, project_id: str) -> list[Task]:
        try:
            rows = self._db.conn.execute(
                "SELECT * FROM tasks WHERE project_id = ? ORDER BY rowid ASC", (project_id,)
            ).fetchall()
            return [self._to_task(r) for r in rows]
        except sqlite3.Error as exc:
            raise StorageError(f"Failed to list tasks: {exc}") from exc

    def get(self, task_id: str, project_id: str) -> Task | None:
        try:
            row = self._db.conn.execute(
                "SELECT * FROM tasks WHERE id = ? AND project_id = ?", (task_id, project_id)
            ).fetchone()
            return self._to_task(row) if row else None
        except sqlite3.Error as exc:
            raise StorageError(f"Failed to get task: {exc}") from exc

    @staticmethod
    def _to_task(row: sqlite3.Row) -> Task:
        return Task(
            id=row["id"],
            description=row["description"],
            priority=TaskPriority(row["priority"]),
            status=TaskStatus(row["status"]),
            depends_on=json.loads(row["depends_on"]),
            files=json.loads(row["files"]),
            acceptance_criteria=json.loads(row["acceptance_criteria"]),
            attempts=row["attempts"],
            created_at=_dt(row["created_at"]) or datetime.now(UTC),
            updated_at=_dt(row["updated_at"]) or datetime.now(UTC),
            result=row["result"],
        )


class EventRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def insert(self, event: Event) -> None:
        try:
            self._db.conn.execute(
                "INSERT INTO events (ts, type, run_id, data) VALUES (?, ?, ?, ?)",
                (event.ts.isoformat(), event.type.value, event.run_id, json.dumps(event.data, default=str)),
            )
            self._db.conn.commit()
        except sqlite3.Error as exc:
            raise StorageError(f"Failed to insert event: {exc}") from exc

    def count(self) -> int:
        try:
            row = self._db.conn.execute("SELECT COUNT(*) FROM events").fetchone()
            return row[0] if row else 0
        except sqlite3.Error as exc:
            raise StorageError(f"Failed to count events: {exc}") from exc

    def recent(self, limit: int = 50) -> list[Event]:
        try:
            rows = self._db.conn.execute(
                "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [
                Event(
                    ts=_dt(r["ts"]) or datetime.now(UTC),
                    type=EventType(r["type"]),
                    run_id=r["run_id"],
                    data=json.loads(r["data"]),
                )
                for r in rows
            ]
        except sqlite3.Error as exc:
            raise StorageError(f"Failed to get recent events: {exc}") from exc


class ErrorRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def insert(self, error: ErrorRecord, project_id: str) -> None:
        try:
            self._db.conn.execute(
                """
                INSERT INTO errors (project_id, run_id, ts, source, kind, message, detail)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    error.run_id,
                    _iso(error.ts),
                    error.source,
                    error.kind,
                    error.message,
                    json.dumps(error.detail, default=str) if error.detail else None,
                ),
            )
            self._db.conn.commit()
        except sqlite3.Error as exc:
            raise StorageError(f"Failed to insert error: {exc}") from exc

    def list(self, project_id: str, limit: int = 50) -> list[ErrorRecord]:
        try:
            rows = self._db.conn.execute(
                "SELECT * FROM errors WHERE project_id = ? ORDER BY id DESC LIMIT ?",
                (project_id, limit),
            ).fetchall()
            return [
                ErrorRecord(
                    ts=_dt(r["ts"]) or datetime.now(UTC),
                    source=r["source"],
                    kind=r["kind"],
                    message=r["message"],
                    run_id=r["run_id"],
                    detail=json.loads(r["detail"]) if r["detail"] else None,
                )
                for r in rows
            ]
        except sqlite3.Error as exc:
            raise StorageError(f"Failed to list errors: {exc}") from exc


class ModelUsageRepository:
    """Persists per-call model usage (spec sections 40, 41)."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def insert(self, record: ModelUsageRecord) -> None:
        try:
            self._db.conn.execute(
                """
                INSERT INTO model_usage (ts, run_id, agent, provider, model,
                                         input_tokens, output_tokens, total_tokens,
                                         latency_ms, attempts, success, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _iso(record.ts),
                    record.run_id,
                    record.agent,
                    record.provider,
                    record.model,
                    record.input_tokens,
                    record.output_tokens,
                    record.total_tokens,
                    record.latency_ms,
                    record.attempts,
                    int(record.success),
                    record.error,
                ),
            )
            self._db.conn.commit()
        except sqlite3.Error as exc:
            raise StorageError(f"Failed to record model usage: {exc}") from exc

    def recent(self, run_id: str | None = None, limit: int = 50) -> list[ModelUsageRecord]:
        sql = "SELECT * FROM model_usage"
        params: list[Any] = []
        if run_id is not None:
            sql += " WHERE run_id = ?"
            params.append(run_id)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        try:
            rows = self._db.conn.execute(sql, params).fetchall()
            return [self._to_record(row) for row in rows]
        except sqlite3.Error as exc:
            raise StorageError(f"Failed to read model usage: {exc}") from exc

    def totals(self) -> dict[str, Any]:
        try:
            row = self._db.conn.execute(
                """
                SELECT COUNT(*) as calls,
                       SUM(input_tokens) as input_tokens,
                       SUM(output_tokens) as output_tokens,
                       SUM(total_tokens) as total_tokens
                FROM model_usage
                """
            ).fetchone()
            if not row:
                return {"calls": 0, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
            return {
                "calls": row["calls"] or 0,
                "input_tokens": row["input_tokens"],
                "output_tokens": row["output_tokens"],
                "total_tokens": row["total_tokens"],
            }
        except sqlite3.Error as exc:
            raise StorageError(f"Failed to calculate usage totals: {exc}") from exc

    @staticmethod
    def _to_record(row: sqlite3.Row) -> ModelUsageRecord:
        return ModelUsageRecord(
            ts=_dt(row["ts"]) or datetime.now(UTC),
            run_id=row["run_id"],
            agent=row["agent"],
            provider=row["provider"],
            model=row["model"],
            input_tokens=row["input_tokens"],
            output_tokens=row["output_tokens"],
            total_tokens=row["total_tokens"],
            latency_ms=row["latency_ms"],
            attempts=row["attempts"],
            success=bool(row["success"]),
            error=row["error"],
        )


class CheckpointRepository:
    """Persists checkpoint metadata (spec section 21)."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def insert(self, record: CheckpointRecord) -> None:
        try:
            self._db.conn.execute(
                """
                INSERT INTO checkpoints (id, project_id, label, git_commit,
                                         description, created_at, run_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.project_id,
                    record.label,
                    record.git_commit,
                    record.description,
                    _iso(record.created_at),
                    record.run_id,
                ),
            )
            self._db.conn.commit()
        except sqlite3.Error as exc:
            raise StorageError(f"Failed to persist checkpoint: {exc}") from exc

    def get(self, checkpoint_id: str) -> CheckpointRecord | None:
        try:
            row = self._db.conn.execute(
                "SELECT * FROM checkpoints WHERE id = ?", (checkpoint_id,)
            ).fetchone()
            return self._to_record(row) if row else None
        except sqlite3.Error as exc:
            raise StorageError(f"Failed to read checkpoint: {exc}") from exc

    def latest(self, project_id: str) -> CheckpointRecord | None:
        try:
            row = self._db.conn.execute(
                """
                SELECT * FROM checkpoints WHERE project_id = ?
                ORDER BY created_at DESC, rowid DESC LIMIT 1
                """,
                (project_id,),
            ).fetchone()
            return self._to_record(row) if row else None
        except sqlite3.Error as exc:
            raise StorageError(f"Failed to read latest checkpoint: {exc}") from exc

    def list(self, project_id: str, limit: int = 20) -> list[CheckpointRecord]:
        try:
            rows = self._db.conn.execute(
                """
                SELECT * FROM checkpoints WHERE project_id = ?
                ORDER BY created_at DESC, rowid DESC LIMIT ?
                """,
                (project_id, limit),
            ).fetchall()
            return [self._to_record(r) for r in rows]
        except sqlite3.Error as exc:
            raise StorageError(f"Failed to list checkpoints: {exc}") from exc

    @staticmethod
    def _to_record(row: sqlite3.Row) -> CheckpointRecord:
        return CheckpointRecord(
            id=row["id"],
            project_id=row["project_id"],
            label=row["label"],
            git_commit=row["git_commit"],
            description=row["description"],
            created_at=_dt(row["created_at"]) or datetime.now(UTC),
            run_id=row["run_id"],
        )
