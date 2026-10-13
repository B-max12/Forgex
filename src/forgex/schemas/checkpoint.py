"""Checkpoint metadata (spec section 21)."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class CheckpointRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    project_id: str
    label: str
    git_commit: str | None = None
    description: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    run_id: str | None = None
