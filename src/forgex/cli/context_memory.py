"""Conversational memory and follow-up context tracker for FORGEX Universal CLI."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

FOLLOWUP_PATTERNS = [
    r"\b(?:it|that|those|them|these)\b",
    r"\b(?:now\s+add|also\s+add|and\s+also|next\s+add)\b",
    r"\b(?:fix\s+the\s+test|fix\s+tests?|make\s+it\s+pass)\b",
    r"\b(?:refactor\s+it|update\s+it|change\s+it)\b",
    r"\b(?:same\s+thing|previous\s+task)\b",
]


@dataclass
class ConversationContext:
    """Maintains recent task context across interactive prompts."""

    history: list[str] = field(default_factory=list)
    last_request: str | None = None
    last_changed_files: list[str] = field(default_factory=list)
    last_status: str | None = None
    last_checkpoint_id: str | None = None

    def record_run(
        self,
        request: str,
        status: str,
        changed_files: list[str],
        checkpoint_id: str | None = None,
    ) -> None:
        """Update context memory with latest execution results."""
        self.history.append(request)
        self.last_request = request
        self.last_status = status
        self.last_changed_files = list(changed_files)
        self.last_checkpoint_id = checkpoint_id

    def is_followup(self, text: str) -> bool:
        """Detect if the new prompt refers back to the previous conversation context."""
        if not self.last_request:
            return False
        clean = text.strip().lower()
        return any(re.search(pat, clean) for pat in FOLLOWUP_PATTERNS)

    def enrich_request(self, request: str) -> str:
        """If request is a follow-up, prepend context from previous runs."""
        clean = request.strip()
        if not self.is_followup(clean):
            return clean

        context_parts = []
        if self.last_request:
            context_parts.append(f"Previous task: {self.last_request}")
        if self.last_changed_files:
            file_sample = ", ".join(self.last_changed_files[:5])
            context_parts.append(f"Modified files: {file_sample}")

        context_str = " | ".join(context_parts)
        return f"[Context: {context_str}] {clean}"
