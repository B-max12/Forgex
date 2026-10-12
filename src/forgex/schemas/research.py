"""Research metadata (spec section 8).

Research never invents facts: every note records where it came from and
when it was checked — or is explicitly marked unavailable.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ResearchNote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str
    source: str  # "pypi" | "npm" | "crates" | "go" | "none"
    summary: str
    version: str | None = None
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    confidence: Literal["high", "medium", "low"] = "medium"
    available: bool = True
    detail: str | None = None  # registry URL, or the unavailability reason
