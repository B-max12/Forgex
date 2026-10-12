"""Result schemas — model usage records and command verification outcomes (spec sections 40, 41, 56).

Token counts are stored exactly as reported by the provider. When usage
is not reported, values stay None — never fabricated (spec section 41).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pydantic import BaseModel, ConfigDict, Field


class ModelUsageRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    run_id: str | None = None
    agent: str
    provider: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    latency_ms: float | None = None
    attempts: int = 1
    success: bool = True
    error: str | None = None


class CommandOutcome(BaseModel):
    """One executed command's outcome (tests/build/lint). `output_tail` is the
    last few KB — not the full stream (spec section 16)."""

    model_config = ConfigDict(extra="forbid")

    command: list[str] = Field(default_factory=list)
    exit_code: int | None = None  # None = never ran (denied by policy)
    timed_out: bool = False
    duration_ms: float | None = None
    output_tail: str = ""

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


class TestResults(CommandOutcome):
    """Test suite outcome. Counts are parsed when the runner reports them;
    None = unknown — never fabricated (spec section 41)."""

    __test__ = False

    passed: int | None = None
    failed: int | None = None
    errors: int | None = None


class BuildResults(CommandOutcome):
    """Build outcome (compile/packaging step, where applicable)."""


class VerificationOutcome(BaseModel):
    """Deterministic verification results (spec sections 11, 56)."""

    tests: TestResults | None = None
    build: BuildResults | None = None
    lint: CommandOutcome | None = None
