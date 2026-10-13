"""Research engine (spec sections 8, 73).

Routes topics to registry sources. Prefixed topics ("pypi:fastapi") go
straight to that registry; plain names try sources in order (Python-first).
When research is disabled in config, every topic returns an
explicit 'unavailable' note instead of touching the network.
"""

from __future__ import annotations

import logging

import httpx

from forgex.config.schema import ForgexConfig
from forgex.research.sources import (
    CratesSource,
    GoSource,
    NpmSource,
    PyPISource,
    RegistrySource,
    _unavailable,
)
from forgex.schemas.research import ResearchNote

logger = logging.getLogger("forgex.research")

MAX_TOPICS = 8


class ResearchEngine:
    def __init__(
        self,
        *,
        config: ForgexConfig | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._client = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(10.0), headers={"User-Agent": "forgex-research/0.1"}
        )
        self._owns_client = http_client is None
        self._sources: list[RegistrySource] = [
            PyPISource(),
            NpmSource(),
            CratesSource(),
            GoSource(),
        ]
        self._by_ecosystem = {s.ecosystem: s for s in self._sources}
        self._enabled = config.research.enabled if config is not None else True

    async def research(self, topics: list[str]) -> list[ResearchNote]:
        cleaned = [t.strip() for t in topics if t and t.strip()]
        # Prioritize package-like identifiers over long descriptive sentences
        package_like = [t for t in cleaned if " " not in t]
        phrase_like = [t for t in cleaned if " " in t]
        selected = (package_like + phrase_like)[:MAX_TOPICS]

        if not selected:
            return []
        if not self._enabled:
            return [
                _unavailable(topic, "research disabled in configuration (offline mode)")
                for topic in selected
            ]
        return [await self._lookup(topic) for topic in selected]

    async def _lookup(self, topic: str) -> ResearchNote:
        clean = topic.strip()
        ecosystem, sep, name = clean.partition(":")
        if sep and ecosystem in self._by_ecosystem:
            return await self._safe_lookup(self._by_ecosystem[ecosystem], name.strip(), clean)
        # Plain multi-word phrases cannot be package names in any registry
        if " " in clean:
            return _unavailable(
                clean,
                "topic is a descriptive phrase; research queries package registries for package names",
            )
        for source in self._sources:
            note = await self._safe_lookup(source, clean, clean)
            if note.available:
                return note
        return _unavailable(clean, "not found in any registry source (pypi, npm, crates, go)")

    async def _safe_lookup(
        self, source: RegistrySource, name: str, topic: str
    ) -> ResearchNote:
        try:
            return await source.lookup(name, self._client)
        except Exception:
            logger.warning("research source %s failed for %r", source.ecosystem, topic, exc_info=True)
            return _unavailable(topic, f"{source.ecosystem} lookup failed unexpectedly")

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
