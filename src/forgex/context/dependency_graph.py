"""Import dependency graph (spec section 17)."""

from __future__ import annotations

import posixpath
from collections import defaultdict, deque
from typing import Any

from forgex.context.indexer import IndexData


def _match(files: dict[str, Any], candidates: list[str]) -> str | None:
    for c in candidates:
        if c in files:
            return c
    # Try searching suffix match across all project files
    for c in candidates:
        matching = [f for f in files if f.endswith("/" + c) or f == c]
        if matching:
            return min(matching, key=len)
    return None


def _resolve_python(imp: str, importer_rel: str, files: dict[str, Any]) -> str | None:
    importer_dir = posixpath.dirname(importer_rel)
    if imp.startswith("."):
        # Relative import
        level = len(imp) - len(imp.lstrip("."))
        sub = imp.lstrip(".").replace(".", "/")
        target_dir = importer_dir
        for _ in range(level - 1):
            target_dir = posixpath.dirname(target_dir)
        base = posixpath.normpath(posixpath.join(target_dir, sub)) if sub else target_dir
        return _match(files, [f"{base}.py", f"{base}/__init__.py"])

    # Absolute import
    base = imp.replace(".", "/")
    return _match(files, [f"{base}.py", f"{base}/__init__.py"])


def _resolve_js(imp: str, importer_rel: str, files: dict[str, Any]) -> str | None:
    if not imp.startswith("."):
        return None  # External package
    importer_dir = posixpath.dirname(importer_rel)
    base = posixpath.normpath(posixpath.join(importer_dir, imp))
    candidates = [
        base,
        f"{base}.js",
        f"{base}.jsx",
        f"{base}.ts",
        f"{base}.tsx",
        f"{base}/index.js",
        f"{base}/index.ts",
    ]
    return _match(files, candidates)


class DependencyGraph:
    def __init__(self, index: IndexData) -> None:
        self._index = index
        self._imports: dict[str, list[str]] = defaultdict(list)
        self._importers: dict[str, list[str]] = defaultdict(list)
        self._build_graph()

    def _build_graph(self) -> None:
        files = self._index.files
        for rel_path, entry in files.items():
            for raw_import in entry.imports:
                target = None
                if entry.language == "python":
                    target = _resolve_python(raw_import, rel_path, files)
                elif entry.language in ("javascript", "typescript"):
                    target = _resolve_js(raw_import, rel_path, files)
                if target and target != rel_path:
                    if target not in self._imports[rel_path]:
                        self._imports[rel_path].append(target)
                    if rel_path not in self._importers[target]:
                        self._importers[target].append(rel_path)

    def imports_of(self, file: str, max_depth: int = 1) -> dict[str, int]:
        results: dict[str, int] = {}
        queue: deque[tuple[str, int]] = deque([(file, 0)])
        seen = {file}

        while queue:
            curr, depth = queue.popleft()
            if depth >= max_depth:
                continue
            for target in self._imports.get(curr, []):
                if target not in seen:
                    seen.add(target)
                    results[target] = depth + 1
                    queue.append((target, depth + 1))
        return results

    def importers_of(self, file: str, max_depth: int = 1) -> dict[str, int]:
        results: dict[str, int] = {}
        queue: deque[tuple[str, int]] = deque([(file, 0)])
        seen = {file}

        while queue:
            curr, depth = queue.popleft()
            if depth >= max_depth:
                continue
            for importer in self._importers.get(curr, []):
                if importer not in seen:
                    seen.add(importer)
                    results[importer] = depth + 1
                    queue.append((importer, depth + 1))
        return results
