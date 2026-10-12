"""Lexical relevance retrieval with auditable reasons (spec section 16)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from forgex.context.dependency_graph import DependencyGraph
from forgex.context.indexer import IndexData

STOPWORDS = {
    "the", "and", "for", "with", "into", "from", "this", "that", "must",
    "should", "will", "your", "are", "all", "not", "but", "can", "has",
    "have", "when", "which", "was", "you", "its", "our",
}
_CAMEL_RE = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])")


def query_terms(text: str, *, limit: int = 12) -> list[str]:
    terms: list[str] = []
    for token in re.findall(r"[A-Za-z][A-Za-z0-9_]{2,}", text):
        for part in _CAMEL_RE.findall(token.replace("_", " ")) or [token]:
            p = part.lower()
            if len(p) >= 3 and p not in STOPWORDS and p not in terms:
                terms.append(p)
        snake = token.lower().replace("_", " ").split()
        for p in snake:
            if len(p) >= 3 and p not in STOPWORDS and p not in terms:
                terms.append(p)
    return terms[:limit]


@dataclass
class ScoredFile:
    path: str
    score: int = 0
    reasons: list[str] = field(default_factory=list)

    def bump(self, points: int, reason: str) -> None:
        self.score += points
        self.reasons.append(reason)


def _path_tokens(path: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", path.lower()) if len(t) >= 3}


def _is_test_path(path: str) -> bool:
    return "test" in path.lower()


def score_files(
    *,
    index: IndexData,
    graph: DependencyGraph,
    query: str,
    seeds: list[str],
    recent: list[str] | None = None,
    limit: int = 20,
) -> list[ScoredFile]:
    scores: dict[str, ScoredFile] = {}

    def get(path: str) -> ScoredFile:
        return scores.setdefault(path, ScoredFile(path=path))

    terms = set(query_terms(query))

    for seed in seeds:
        if seed in index.files:
            get(seed).bump(100, "seed file (planned/changed)")
        for importer, depth in graph.importers_of(seed, max_depth=2).items():
            if importer in index.files:
                points = 50 if depth == 1 else 15
                get(importer).bump(points, f"imports seed ({'direct' if depth == 1 else 'transitive'})")
        for dependency in graph.imports_of(seed, max_depth=1):
            if dependency in index.files:
                get(dependency).bump(30, "imported by seed")
        seed_tokens = _path_tokens(seed)
        if seed_tokens:
            for path in index.files:
                if _is_test_path(path) and _path_tokens(path) & seed_tokens:
                    get(path).bump(30, f"test file for {seed}")

    for path in recent or []:
        if path in index.files:
            get(path).bump(20, "recently changed")

    for path, entry in index.files.items():
        lowered = path.lower()
        for term in terms:
            if term in lowered:
                get(path).bump(5, f"path matches '{term}'")
            for symbol in entry.symbols:
                if term in symbol.name.lower():
                    get(path).bump(10, f"symbol '{symbol.name}' matches '{term}'")
                    break

    ranked = sorted(scores.values(), key=lambda s: (-s.score, s.path))
    return [s for s in ranked if s.score > 0][:limit]
