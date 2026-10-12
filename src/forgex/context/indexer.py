"""Project indexer: symbols, imports, and file metadata (spec section 17)."""

from __future__ import annotations

import ast
import os
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from forgex.tools.filesystem import IGNORED_DIRS, is_secret_file

INDEX_VERSION = 1
MAX_PARSE_BYTES = 500_000
MAX_SYMBOLS_PER_FILE = 100
MAX_IMPORTS_PER_FILE = 50

LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".json": "json",
    ".toml": "toml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".md": "markdown",
    ".txt": "text",
}

PARSEABLE = {"python", "javascript", "typescript"}


class SymbolInfo(BaseModel):
    name: str
    kind: str  # function | class | method | export
    line: int


class FileIndex(BaseModel):
    size: int
    mtime: float
    language: str
    symbols: list[SymbolInfo] = Field(default_factory=list)
    imports: list[str] = Field(default_factory=list)


class IndexData(BaseModel):
    version: int = INDEX_VERSION
    generated_at: str
    files: dict[str, FileIndex] = Field(default_factory=dict)
    stats: dict[str, int] = Field(default_factory=dict)


def iter_project_files(workspace: Path) -> Iterator[Path]:
    for root, dirs, files in os.walk(workspace):
        # Mutate dirs in place to prevent descending into ignored dirs
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
        for f in files:
            if is_secret_file(f):
                continue
            path = Path(root) / f
            yield path


def _python_parse(source: str) -> tuple[list[SymbolInfo], list[str]]:
    symbols: list[SymbolInfo] = []
    imports: list[str] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return [], []

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.append(SymbolInfo(name=node.name, kind="function", line=node.lineno))
        elif isinstance(node, ast.ClassDef):
            symbols.append(SymbolInfo(name=node.name, kind="class", line=node.lineno))
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    symbols.append(
                        SymbolInfo(name=f"{node.name}.{child.name}", kind="method", line=child.lineno)
                    )

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            prefix = "." * node.level
            if node.module:
                imports.append(prefix + node.module)
            else:
                for alias in node.names:
                    imports.append(prefix + alias.name)

    return symbols[:MAX_SYMBOLS_PER_FILE], imports[:MAX_IMPORTS_PER_FILE]


_JS_IMPORT_RE = re.compile(
    r"""(?:(?:import|export)\s+[^;\n]*?\s+from\s+|import\s+|require\s*\(\s*|import\s*\(\s*)['"]([^'"]+)['"]"""
)
_JS_SYMBOL_RE = re.compile(
    r"export\s+(?:default\s+)?(?:async\s+)?(?:function|class|const|let)\s+(\w+)"
)


def _js_parse(source: str) -> tuple[list[SymbolInfo], list[str]]:
    imports = _JS_IMPORT_RE.findall(source)[:MAX_IMPORTS_PER_FILE]
    symbols = [
        SymbolInfo(name=name, kind="export", line=0)
        for name in _JS_SYMBOL_RE.findall(source)[:MAX_SYMBOLS_PER_FILE]
    ]
    return symbols, imports


def index_file(path: Path, rel: str, size: int, mtime: float) -> FileIndex:
    language = LANGUAGE_BY_SUFFIX.get(path.suffix.lower(), "other")
    entry = FileIndex(size=size, mtime=mtime, language=language)
    if language in PARSEABLE and size <= MAX_PARSE_BYTES:
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return entry
        symbols, imports = _python_parse(source) if language == "python" else _js_parse(source)
        entry.symbols, entry.imports = symbols, imports
    return entry


def build(workspace: Path, cached: IndexData | None = None) -> IndexData:
    workspace = workspace.resolve()
    cached_files = cached.files if cached and cached.version == INDEX_VERSION else {}
    files: dict[str, FileIndex] = {}
    parsed = reused = 0

    for path in iter_project_files(workspace):
        rel = path.relative_to(workspace).as_posix()
        try:
            stat = path.stat()
        except OSError:
            continue
        old = cached_files.get(rel)
        if old is not None and old.size == stat.st_size and old.mtime == stat.st_mtime:
            files[rel] = old
            reused += 1
            continue
        files[rel] = index_file(path, rel, stat.st_size, stat.st_mtime)
        parsed += 1

    pruned = max(0, len(cached_files) - reused)
    return IndexData(
        generated_at=datetime.now(UTC).isoformat(),
        files=files,
        stats={"parsed": parsed, "reused": reused, "pruned": pruned},
    )
