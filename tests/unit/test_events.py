from __future__ import annotations

import json

from forgex.orchestration.events import EventRecorder, read_events
from forgex.schemas.event import Event, EventType
from forgex.storage.database import Database
from forgex.storage.repositories import EventRepository


def test_record_appends_jsonl(tmp_path):
    recorder = EventRecorder(tmp_path / "events.jsonl")
    event = recorder.record(EventType.RUN_STARTED, {"request": "demo"})
    lines = (tmp_path / "events.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1
    raw = json.loads(lines[0])
    assert raw["type"] == "RunStarted"
    assert raw["data"] == {"request": "demo"}
    assert raw["run_id"] is None
    assert event.type is EventType.RUN_STARTED


def test_record_persists_to_sqlite(tmp_path):
    db = Database(tmp_path / "state.db")
    repo = EventRepository(db)
    recorder = EventRecorder(tmp_path / "events.jsonl", repository=repo)
    recorder.record(EventType.TASK_COMPLETED, {"task": "TASK-001"}, run_id="run-abc")
    assert repo.count() == 1
    recent = repo.recent(limit=10)
    assert recent[0].type is EventType.TASK_COMPLETED
    assert recent[0].run_id == "run-abc"
    db.close()


def test_subscribers_notified_then_unsubscribed(tmp_path):
    recorder = EventRecorder(tmp_path / "events.jsonl")
    seen: list[Event] = []
    unsubscribe = recorder.subscribe(seen.append)
    recorder.record(EventType.AGENT_STARTED, {"agent": "architect"})
    unsubscribe()
    recorder.record(EventType.AGENT_STARTED, {"agent": "builder"})
    assert [e.data["agent"] for e in seen] == ["architect"]


def test_broken_subscriber_does_not_break_recording(tmp_path):
    recorder = EventRecorder(tmp_path / "events.jsonl")

    def bad(_event: Event) -> None:
        raise RuntimeError("boom")

    recorder.subscribe(bad)
    recorder.record(EventType.FILE_CHANGED, {"path": "x"})
    assert len(read_events(tmp_path / "events.jsonl")) == 1


def test_read_events_limit_and_filter(tmp_path):
    path = tmp_path / "events.jsonl"
    recorder = EventRecorder(path)
    for i in range(5):
        etype = EventType.AGENT_STARTED if i % 2 == 0 else EventType.TOOL_STARTED
        recorder.record(etype, {"i": i})
    assert len(read_events(path)) == 5
    last_two = read_events(path, limit=2)
