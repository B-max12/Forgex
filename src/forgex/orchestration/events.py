"""Event system (spec section 24)."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from forgex.schemas.event import Event, EventType
from forgex.storage.repositories import EventRepository

logger = logging.getLogger("forgex.events")


class EventRecorder:
    def __init__(
        self,
        path: Path,
        repository: EventRepository | None = None,
    ) -> None:
        self._path = Path(path)
        self._repo = repository
        self._subscribers: list[Callable[[Event], None]] = []
        self.default_run_id: str | None = None

    def subscribe(self, callback: Callable[[Event], None]) -> Callable[[], None]:
        self._subscribers.append(callback)

        def _unsubscribe() -> None:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

        return _unsubscribe

    def record(
        self,
        type_: EventType,
        data: dict[str, Any] | None = None,
        *,
        run_id: str | None = None,
    ) -> Event:
        """Append one event (durable first), index it, notify subscribers."""
        event = Event(
            type=type_,
            data=data or {},
            run_id=run_id or self.default_run_id,
        )
        # 1. Durable append (fsync — interrupt-safe, spec section 36).
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(event.to_jsonl() + "\n")
            fh.flush()
            os.fsync(fh.fileno())

        # 2. Query index (best-effort — rebuildable).
        if self._repo is not None:
            try:
                self._repo.insert(event)
            except Exception:
                logger.warning("Event SQLite index write failed for %s", event.type.value, exc_info=True)

        # 3. Subscribers (a broken subscriber must never kill a run).
        for callback in list(self._subscribers):
            try:
                callback(event)
            except Exception:
                logger.warning("Event subscriber raised; continuing", exc_info=True)

        return event


def read_events(
    path: Path,
    *,
    limit: int | None = None,
    event_type: EventType | None = None,
) -> list[Event]:
    """Read events from a JSONL file.

    Malformed lines are skipped with a warning. `limit` returns the LAST n events.
    """
    if not path.is_file():
        return []
    events: list[Event] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = Event.from_jsonl(line)
        except (KeyError, ValueError):
            logger.warning("Skipping malformed event line in %s", path)
            continue
        if event_type is not None and event.type is not event_type:
            continue
        events.append(event)
    if limit is not None:
        return events[-limit:] if limit > 0 else []
    return events
