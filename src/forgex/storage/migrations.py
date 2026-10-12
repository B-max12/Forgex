"""Forward-only schema migrations for the project database.

  v1 (Phase 2): projects, runs, tasks, events, errors
  v2 (Phase 3): model_usage
  v3 (Phase 6): checkpoints
"""

from __future__ import annotations

import sqlite3

SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS projects (
    project_id TEXT PRIMARY KEY,
    path       TEXT NOT NULL,
    name       TEXT NOT NULL,
    status     TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    run_id      TEXT PRIMARY KEY,
    project_id  TEXT NOT NULL REFERENCES projects(project_id),
    request     TEXT NOT NULL,
    status      TEXT NOT NULL,
    phase       TEXT NOT NULL,
    iteration   INTEGER NOT NULL DEFAULT 0,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    summary     TEXT,
    error       TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_project ON runs(project_id);

CREATE TABLE IF NOT EXISTS tasks (
    id                  TEXT NOT NULL,
    project_id          TEXT NOT NULL REFERENCES projects(project_id),
    description         TEXT NOT NULL,
    priority            TEXT NOT NULL DEFAULT 'medium',
    status              TEXT NOT NULL DEFAULT 'pending',
    depends_on          TEXT NOT NULL DEFAULT '[]',
    files               TEXT NOT NULL DEFAULT '[]',
    acceptance_criteria TEXT NOT NULL DEFAULT '[]',
    attempts            INTEGER NOT NULL DEFAULT 0,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    result              TEXT,
    PRIMARY KEY (id, project_id)
);
CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);

CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         TEXT NOT NULL,
    type       TEXT NOT NULL,
    run_id     TEXT,
    data       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(type);

CREATE TABLE IF NOT EXISTS errors (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES projects(project_id),
    run_id     TEXT,
    ts         TEXT NOT NULL,
    source     TEXT NOT NULL,
    kind       TEXT NOT NULL,
    message    TEXT NOT NULL,
    detail     TEXT
);
"""

SCHEMA_V2 = """
CREATE TABLE IF NOT EXISTS model_usage (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT NOT NULL,
    run_id        TEXT,
    agent         TEXT NOT NULL,
    provider      TEXT NOT NULL,
    model         TEXT NOT NULL,
    input_tokens  INTEGER,
    output_tokens INTEGER,
    total_tokens  INTEGER,
    latency_ms    REAL,
    attempts      INTEGER NOT NULL DEFAULT 1,
    success       INTEGER NOT NULL DEFAULT 1,
    error         TEXT
);
CREATE INDEX IF NOT EXISTS idx_model_usage_run ON model_usage(run_id);
"""

SCHEMA_V3 = """
CREATE TABLE IF NOT EXISTS checkpoints (
    id          TEXT PRIMARY KEY,
    project_id  TEXT NOT NULL,
    label       TEXT NOT NULL,
    git_commit  TEXT,
    description TEXT,
    created_at  TEXT NOT NULL,
    run_id      TEXT
);
CREATE INDEX IF NOT EXISTS idx_checkpoints_project ON checkpoints(project_id);
"""

MIGRATIONS: list[tuple[int, str]] = [
    (1, SCHEMA_V1),
    (2, SCHEMA_V2),
    (3, SCHEMA_V3),
]


def run_migrations(conn: sqlite3.Connection) -> int:
    """Run all unapplied migrations in order. Returns the current schema version."""
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)")
    row = conn.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1").fetchone()
    current_version = row[0] if row else 0

    for version, script in MIGRATIONS:
        if version > current_version:
            conn.executescript(script)
            conn.execute("INSERT OR REPLACE INTO schema_version (version) VALUES (?)", (version,))
            conn.commit()
            current_version = version

    return current_version
