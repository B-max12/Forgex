"""Secret redaction (spec sections 46, 75).

Secrets must never leak into logs, events, errors, or the database. Any
code formatting external text passes through redact() or redact_patterns()
with known secrets.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

MASK = "***REDACTED***"

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"gsk_[A-Za-z0-9]{20,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"ghp_[A-Za-z0-9]{30,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"glpat-[A-Za-z0-9_-]{20,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    re.compile(
        r"(?i)\b(api[_-]?key|secret|token|password|passwd)\b['\"]?\s*[:=]\s*['\"][^'\"\n]{8,}['\"]"
    ),
)


def redact(text: str, secrets: Iterable[str | None]) -> str:
    """Replace every occurrence of each secret with the mask."""
    result = text
    for secret in secrets:
        if secret and len(secret) >= 4:
            result = result.replace(secret, MASK)
    return result


def redact_patterns(text: str) -> str:
    """Scrub secret-looking content before it enters model context (§46).
    Applied at every content-on-ramp: read_file, search, prefetch, context."""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(MASK, text)
    return text
