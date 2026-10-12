"""Research package (spec section 8): official-registry lookups only."""

from forgex.research.citations import format_note, format_notes
from forgex.research.engine import ResearchEngine
from forgex.research.sources import CratesSource, GoSource, NpmSource, PyPISource

__all__ = [
    "CratesSource",
    "GoSource",
    "NpmSource",
    "PyPISource",
    "ResearchEngine",
    "format_note",
    "format_notes",
]
