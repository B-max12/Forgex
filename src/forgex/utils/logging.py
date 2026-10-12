"""Internal logging for FORGEX.

Diagnostics go to stderr so stdout stays clean for --json and piped
output. Human-facing rendering lives in :mod:`forgex.cli.ui`.
"""

from __future__ import annotations

import logging

_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}


def configure_logging(level: str = "warning") -> None:
    """Configure the root ``forgex`` logger with a stderr handler."""
    logger = logging.getLogger("forgex")
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S")
    )
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(_LEVELS.get(level.lower(), logging.WARNING))
