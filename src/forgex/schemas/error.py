"""FORGEX error taxonomy and the persisted error record (spec sections 5, 25, 28).

All controlled failures derive from :class:`ForgexError` so the CLI can
render friendly messages and keep raw stack traces behind ``--debug``.
Exit codes are stable per error class.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


try:
    import click
    _BaseError = click.ClickException
except ImportError:
    try:
        import typer._click as _click
        _BaseError = _click.ClickException
    except Exception:
        _BaseError = Exception


class ForgexError(_BaseError):
    """Base class for all controlled FORGEX errors."""

    exit_code: int = 1

    def __init__(self, message: str = "") -> None:
        super().__init__(message)


class ConfigError(ForgexError):
    exit_code = 2


class FileSystemError(ForgexError):
    exit_code = 3


class ProjectError(ForgexError):
    exit_code = 4


class ProviderError(ForgexError):
    """Provider-level failure. `retryable` drives the retry policy (§29);
    `attempts` records how many attempts were made (§40)."""

    exit_code = 5
    default_retryable: bool = False
    attempts: int = 1

    def __init__(self, message: str, *, retryable: bool | None = None, attempts: int = 1) -> None:
        super().__init__(message)
        self.retryable = self.default_retryable if retryable is None else retryable
        self.attempts = attempts


class AuthenticationError(ProviderError):
    exit_code = 6
    default_retryable = False


class RateLimitError(ProviderError):
    exit_code = 7
    default_retryable = True


class ToolError(ForgexError):
    exit_code = 8


class PermissionDeniedError(ToolError):
    """An agent attempted an action outside its permission set."""
    exit_code = 8


class SandboxError(ForgexError):
    exit_code = 9


class CommandDeniedError(SandboxError):
    """A command was blocked by policy or not approved (spec sections 19, 33)."""
    exit_code = 9


class GitError(ForgexError):
    exit_code = 10


class BuildError(ForgexError):
    exit_code = 11


class TestError(ForgexError):
    exit_code = 12


class WorkflowError(ForgexError):
    exit_code = 14


class TaskGraphError(ForgexError):
    exit_code = 15


class StorageError(ForgexError):
    exit_code = 16


class AgentOutputError(ForgexError):
    """An agent could not produce valid structured output (spec sections 7, 28)."""
    exit_code = 17


class PathViolationError(FileSystemError):
    """A path attempted to escape the authorized workspace."""
    exit_code = 3


class ErrorRecord(BaseModel):
    """Persisted error record for state and history."""

    model_config = ConfigDict(extra="forbid")

    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source: str
    kind: str
    message: str
    run_id: str | None = None
    detail: dict[str, Any] | None = None
