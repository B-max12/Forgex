"""ContextManager (spec section 17): index → retrieve → compress → assemble.

Fail-open by design in callers: context intelligence enhances prompts but
must never block a build. The index cache lives in .forgex/cache/.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from forgex.context import indexer
from forgex.context.chunker import chunk_generic, chunk_python, select_chunks
from forgex.context.dependency_graph import DependencyGraph
from forgex.context.indexer import IndexData
from forgex.context.retriever import ScoredFile, query_terms, score_files
from forgex.utils.paths import PathViolationError, resolve_in_workspace
from forgex.utils.redact import redact_patterns

logger = logging.getLogger("forgex.context")


class ContextFile(BaseModel):
    path: str
    content: str
    truncated: bool = False
    reasons: list[str] = Field(default_factory=list)


class ContextBundle(BaseModel):
    files: list[ContextFile] = Field(default_factory=list)
    stats: dict[str, Any] = Field(default_factory=dict)

    def render(self) -> str:
        sections = []
        for f in self.files:
            trunc = " (compressed)" if f.truncated else ""
            sections.append(f"--- {f.path}{trunc} ---\n{f.content}")
        return "\n\n".join(sections)


class ContextManager:
    CACHE_FILE = "context-index.json"

    def __init__(self, workspace: Path) -> None:
        self.workspace = Path(workspace).resolve()
        self._cache_path = self.workspace / ".forgex" / "cache" / self.CACHE_FILE
        self._index: IndexData | None = None
        self._graph: DependencyGraph | None = None

    def _load_cache(self) -> IndexData | None:
        if not self._cache_path.is_file():
            return None
        try:
            return IndexData.model_validate_json(self._cache_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return None

    def _save_cache(self, index: IndexData) -> None:
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._cache_path.write_text(index.model_dump_json(), encoding="utf-8")
        except OSError:
            pass

    def ensure_index(self, refresh: bool = False) -> IndexData:
        if self._index is not None and not refresh:
            return self._index

        cached = None if refresh else self._load_cache()
        index = indexer.build(self.workspace, cached)
        self._save_cache(index)
        self._index = index
        self._graph = DependencyGraph(index)
        return index

    @property
    def graph(self) -> DependencyGraph:
        if self._graph is None:
            self.ensure_index()
        assert self._graph is not None
        return self._graph

    def symbol_map(self) -> str:
        index = self.ensure_index()
        lines: list[str] = []
        for path, entry in sorted(index.files.items()):
            if entry.symbols:
                names = [f"{s.kind} {s.name}" if s.kind in ("class", "def") else s.name for s in entry.symbols[:10]]
                lines.append(f"{path}: {', '.join(names)}")
        return "\n".join(lines)

    def relevant_files(
        self,
        query: str,
        seeds: list[str],
        recent: list[str] | None = None,
        limit: int = 10,
    ) -> list[ScoredFile]:
        index = self.ensure_index()
        return score_files(
            index=index,
            graph=self.graph,
            query=query,
            seeds=seeds,
            recent=recent,
            limit=limit,
        )

    def importers_of(self, file: str, max_depth: int = 1) -> list[str]:
        self.ensure_index()
        return sorted(self.graph.importers_of(file, max_depth=max_depth).keys())

    def build_context(
        self,
        query: str,
        seeds: list[str],
        budget: int,
        max_files: int = 4,
        exclude: set[str] | None = None,
    ) -> ContextBundle:
        ranked = self.relevant_files(query=query, seeds=seeds, limit=max_files * 2)
        exclude_set = exclude or set()

        files: list[ContextFile] = []
        remaining_budget = budget
        terms = set(query_terms(query))

        for item in ranked:
            if item.path in exclude_set:
                continue
            if len(files) >= max_files or remaining_budget <= 0:
                break

            try:
                real_path = resolve_in_workspace(self.workspace, item.path)
            except PathViolationError:
                continue

            if not real_path.is_file():
                continue

            try:
                source = real_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            source = redact_patterns(source)

            # Chunk and select
            per_file_budget = min(remaining_budget, budget // 2 if len(ranked) > 1 else budget)
            if real_path.suffix.lower() == ".py":
                chunks = chunk_python(source)
            else:
                chunks = chunk_generic(source)

            content, truncated = select_chunks(chunks, terms, max_chars=per_file_budget)
            files.append(
                ContextFile(
                    path=item.path,
                    content=content,
                    truncated=truncated,
                    reasons=item.reasons,
                )
            )
            remaining_budget -= len(content)

        return ContextBundle(
            files=files,
            stats={"budget_used": budget - remaining_budget, "index_files": len(self.ensure_index().files)},
        )
