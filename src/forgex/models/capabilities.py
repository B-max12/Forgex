"""Model capability metadata (spec section 31).

Never assume a model supports a feature: the router reads these and
adapts requests (drops tools / response_format when unsupported).
Unknown models get conservative defaults — honest "unknown", not guesses.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ModelCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    context_window: int | None = None  # None = unknown
    supports_tools: bool = False
    supports_json: bool = False
    supports_streaming: bool = False
    known: bool = False  # False = inferred conservative defaults, not verified
