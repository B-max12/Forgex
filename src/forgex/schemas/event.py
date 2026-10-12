"""Event schema (spec section 24).

On-disk format (.forgex/events.jsonl), one JSON object per line:

    {"ts": "<iso-8601 utc>", "type": "<EventType>", "run_id": null, "data": {...}}

Introduced in Phase 1; ``run_id`` added in Phase 2 (readers tolerate its
absence). This format is FROZEN — treat it as a public contract.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EventType(str, Enum):
    PROJECT_INITIALIZED = "ProjectInitialized"
    RUN_STARTED = "RunStarted"
    RUN_COMPLETED = "RunCompleted"
    RUN_FAILED = "RunFailed"
    AGENT_STARTED = "AgentStarted"
    AGENT_THINKING = "AgentThinking"
    AGENT_COMPLETED = "AgentCompleted"
    TOOL_STARTED = "ToolStarted"
    TOOL_COMPLETED = "ToolCompleted"
    FILE_CHANGED = "FileChanged"
    TASK_STARTED = "TaskStarted"
    TASK_COMPLETED = "TaskCompleted"
    TEST_STARTED = "TestStarted"
    TEST_COMPLETED = "TestCompleted"
    SUPERVISOR_STARTED = "SupervisorStarted"
    REPAIR_STARTED = "RepairStarted"
    RESEARCH_COMPLETED = "ResearchCompleted"
    PLAN_CREATED = "PlanCreated"
    CHECKPOINT_CREATED = "CheckpointCreated"
    CHECKPOINT_ROLLED_BACK = "CheckpointRolledBack"
    ENSEMBLE_COMPLETED = "EnsembleCompleted"
    INTERRUPTED = "Interrupted"


class Event(BaseModel):
    """One immutable event in the FORGEX observability stream."""

    model_config = ConfigDict(extra="forbid")

    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    type: EventType
    data: dict[str, Any] = Field(default_factory=dict)
    run_id: str | None = None

    def to_jsonl(self) -> str:
        return json.dumps(
            {
                "ts": self.ts.isoformat(),
                "type": self.type.value,
                "run_id": self.run_id,
                "data": self.data,
            },
            default=str,
        )

    @classmethod
    def from_jsonl(cls, line: str) -> "Event":
        """Parse one JSONL line. Raises ValueError/KeyError on malformed input."""
        raw = json.loads(line)
        return cls(
            ts=datetime.fromisoformat(raw["ts"]),
            type=EventType(raw["type"]),
            run_id=raw.get("run_id"),
            data=raw.get("data") or {},
        )
