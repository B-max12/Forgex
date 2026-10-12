"""Citation formatting for research notes (spec section 8)."""

from __future__ import annotations

from forgex.schemas.research import ResearchNote


def format_note(note: ResearchNote) -> str:
    if not note.available:
        return f"[{note.source}] {note.topic} — UNAVAILABLE ({note.detail or note.summary})"
    version = f" v{note.version}" if note.version else ""
    return f"[{note.source}] {note.topic}{version} — {note.summary} (confidence: {note.confidence})"


def format_notes(notes: list[ResearchNote]) -> str:
    return "\n".join(format_note(n) for n in notes) or "(no research available)"
