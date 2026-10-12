"""Natural language intent classification for FORGEX REPL."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class IntentAction(str, Enum):
    PLAN = "plan"
    PLAN_AND_BUILD = "plan_and_build"
    AUTONOMOUS = "autonomous"
    BUILD = "build"
    FIX = "fix"
    REVIEW = "review"
    VERIFY = "verify"
    SUPERVISE = "supervise"
    STATUS = "status"
    DOCTOR = "doctor"
    MODELS = "models"
    DIFF = "diff"
    CHECKPOINT = "checkpoint"
    ROLLBACK = "rollback"
    INIT = "init"
    HELP = "help"
    CHAT = "chat"
    UNKNOWN = "unknown"


@dataclass
class IntentResult:
    action: IntentAction
    confidence: float
    command_args: list[str]
    description: str
    pipeline: list[list[str]] = field(default_factory=list)
    raw_request: str = ""

    def __post_init__(self) -> None:
        if not self.pipeline and self.command_args:
            self.pipeline = [self.command_args]


_INTENT_PATTERNS = [
    # Plan and build patterns (e.g. "build me a REST API", "plan and build a service")
    (
        r"^(?:please\s+)?(?:build\s+me\s+|plan\s+and\s+build\s+)(.+)$",
        IntentAction.PLAN_AND_BUILD,
        lambda m: [["plan", m.group(1).strip()], ["build"]],
        "Plan architecture and execute build pipeline",
    ),
    # Dedicated plan patterns
    (
        r"^(?:please\s+)?(?:plan|design|architect|spec|outline)\s+(.+)$",
        IntentAction.PLAN,
        lambda m: [["plan", m.group(1).strip()]],
        "Create an architectural plan",
    ),
    (
        r"^(?:create|implement|add)\s+(?:a|an|the)?\s*(.+)$",
        IntentAction.PLAN,
        lambda m: [["plan", m.group(1).strip()]],
        "Plan and prepare implementation",
    ),
    # Build patterns
    (
        r"^(?:please\s+)?(?:build|execute\s+plan|run\s+build|start\s+build)$",
        IntentAction.BUILD,
        lambda m: [["build"]],
        "Execute full build pipeline",
    ),
    # Fix patterns
    (
        r"^(?:please\s+)?(?:fix|repair|auto-?fix|heal|resolve\s+errors?|debug)(?:\s+(.*))?$",
        IntentAction.FIX,
        lambda m: [["fix"]],
        "Verify, supervise, and auto-repair until green",
    ),
    # Review patterns
    (
        r"^(?:please\s+)?(?:review|audit|check\s+code|inspect\s+changes?)(?:\s+(.*))?$",
        IntentAction.REVIEW,
        lambda m: [["review"]],
        "Run expert code review",
    ),
    # Verify patterns
    (
        r"^(?:please\s+)?(?:verify|test|run\s+tests?|check\s+tests?|lint)(?:\s+(.*))?$",
        IntentAction.VERIFY,
        lambda m: [["verify"]],
        "Run deterministic verification (tests/lint/typecheck)",
    ),
    # Supervise patterns
    (
        r"^(?:please\s+)?(?:supervise|audit\s+and\s+verify|full\s+audit)(?:\s+(.*))?$",
        IntentAction.SUPERVISE,
        lambda m: [["supervise"]],
        "Run full supervision and verification",
    ),
    # Status patterns
    (
        r"^(?:how\s+is\s+the\s+project|show\s+status|status\s+check|project\s+info|where\s+are\s+we)\b.*$",
        IntentAction.STATUS,
        lambda m: [["status"]],
        "Show project status and metrics",
    ),
    # Doctor patterns
    (
        r"^(?:check\s+environment|check\s+system|doctor|health\s+check|diagnose)\b.*$",
        IntentAction.DOCTOR,
        lambda m: [["doctor"]],
        "Run environment diagnostic checks",
    ),
    # Diff patterns
    (
        r"^(?:show\s+diff|git\s+diff|what\s+changed|changes)\b.*$",
        IntentAction.DIFF,
        lambda m: [["diff"]],
        "Show current git diff",
    ),
    # Checkpoint patterns
    (
        r"^(?:create\s+checkpoint|checkpoint|save\s+state|snapshot)(?:\s+(.+))?$",
        IntentAction.CHECKPOINT,
        lambda m: [["checkpoint", m.group(1).strip()]] if m.group(1) else [["checkpoint"]],
        "Create git checkpoint",
    ),
    # Rollback patterns
    (
        r"^(?:rollback|undo|revert\s+changes?)\b.*$",
        IntentAction.ROLLBACK,
        lambda m: [["rollback"]],
        "Reversible rollback to previous checkpoint",
    ),
    # Init patterns
    (
        r"^(?:init|initialize\s+project|create\s+project)\b.*$",
        IntentAction.INIT,
        lambda m: [["init"]],
        "Initialize FORGEX in project directory",
    ),
    # Models patterns
    (
        r"^(?:show\s+models|list\s+models|models?\s+catalog|which\s+models)\b.*$",
        IntentAction.MODELS,
        lambda m: [["models", "catalog"]],
        "List model bindings and catalog",
    ),
    # Help patterns
    (
        r"^(?:what\s+can\s+you\s+do|commands|help\s+me)\b.*$",
        IntentAction.HELP,
        lambda m: [["help"]],
        "Show available commands and usage",
    ),
]


def classify_intent(text: str) -> IntentResult:
    """Classify free-form natural language input into an action and CLI command pipeline."""
    clean = text.strip()
    if not clean:
        return IntentResult(
            action=IntentAction.UNKNOWN,
            confidence=0.0,
            command_args=[],
            description="Empty input",
            raw_request=clean,
        )

    for pattern, action, pipeline_builder, desc in _INTENT_PATTERNS:
        match = re.search(pattern, clean, re.IGNORECASE)
        if match:
            pipeline = pipeline_builder(match)
            command_args = pipeline[0] if pipeline else []
            raw_req = (
                match.group(1).strip()
                if match.groups() and match.group(1) is not None
                else clean
            )
            return IntentResult(
                action=action,
                confidence=0.9,
                command_args=command_args,
                description=desc,
                pipeline=pipeline,
                raw_request=raw_req,
            )

    # Fallback: if text looks like a task or requirement, route to Architect planning
    if len(clean.split()) >= 3:
        args = ["plan", clean]
        return IntentResult(
            action=IntentAction.PLAN,
            confidence=0.6,
            command_args=args,
            description=f"Plan architectural approach for: '{clean}'",
            pipeline=[args],
            raw_request=clean,
        )

    return IntentResult(
        action=IntentAction.UNKNOWN,
        confidence=0.0,
        command_args=[],
        description="Could not determine intent",
        raw_request=clean,
    )
