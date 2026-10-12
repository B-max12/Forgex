"""SQLite access layer (spec section 25).

The project database lives at .forgex/state.db (gitignored): a
rebuildable query index and run history. WAL mode keeps concurrent
readers safe; foreign keys are enforced.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from forgex.storage.migrations import run_migrations


class Database:
    """Lazy-connecting wrapper around a project-local SQLite database."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self.path))
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.execute("PRAGMA busy_timeout = 5000")
            run_migrations(conn)
            self._conn = conn
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
