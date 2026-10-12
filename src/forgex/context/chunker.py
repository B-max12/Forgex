"""Chunking + selection (spec section 16: context compression)."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass

_CAMEL_RE = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])")


@dataclass
class Chunk:
    name: str
    text: str


def chunk_python(source: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return [Chunk("whole-file", source)]

    def node_end(node: ast.AST) -> int:
        return getattr(node, "end_lineno", None) or getattr(node, "lineno", 0)

    def_nodes = [
        n for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    first_def_line = min((n.lineno for n in def_nodes), default=len(source.splitlines()) + 1)
    head_lines = source.splitlines()[: max(first_def_line - 1, 0)]
    if any(line.strip() for line in head_lines):
        chunks.append(Chunk("module-head", "\n".join(head_lines)))

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            lines = source.splitlines()
            body = "\n".join(lines[node.lineno - 1 : node_end(node)])
            kind = "class" if isinstance(node, ast.ClassDef) else "def"
            chunks.append(
                Chunk(node.name, f"# --- {kind} {node.name} (line {node.lineno}) ---\n{body}")
            )

    return chunks or [Chunk("whole-file", source)]


def chunk_generic(source: str, window: int = 80) -> list[Chunk]:
    lines = source.splitlines()
    if len(lines) <= window:
        return [Chunk("whole-file", source)]
    return [
        Chunk(
            f"lines-{i + 1}-{min(i + window, len(lines))}",
            f"# --- lines {i + 1}-{min(i + window, len(lines))} ---\n"
            + "\n".join(lines[i : i + window]),
        )
        for i in range(0, len(lines), window)
    ]


def _tokens(text: str) -> set[str]:
    out: set[str] = set()
    for part in re.split(r"[^A-Za-z0-9]+", text.lower()):
        out.update(p for p in part.split("_") if len(p) >= 3)
    for token in re.findall(r"[A-Za-z]{3,}", text):
        out.update(p.lower() for p in _CAMEL_RE.findall(token))
    return out


def _matches(chunk: Chunk, terms: set[str]) -> bool:
    chunk_terms = _tokens(chunk.name) | _tokens(chunk.text[:2000])
    return bool(chunk_terms & terms)


def select_chunks(chunks: list[Chunk], terms: set[str], max_chars: int) -> tuple[str, bool]:
    total = sum(len(chunk.text) for chunk in chunks)
    if total <= max_chars:
        return "\n\n".join(chunk.text for chunk in chunks), False

    head = next((c for c in chunks if c.name == "module-head"), None)
    ordered: list[Chunk] = []
    if head is not None:
        ordered.append(head)
    rest = [c for c in chunks if c is not head]
    ordered.extend(c for c in rest if _matches(c, terms))
    ordered.extend(c for c in rest if not _matches(c, terms))

    parts: list[str] = []
    used = 0
    for chunk in ordered:
        if used >= max_chars:
            break
        text = chunk.text
        if len(text) > max_chars - used:
            text = text[: max_chars - used] + "\n... [chunk trimmed]"
        parts.append(text)
        used += len(text)

    return "\n... [lines omitted] ...\n".join(parts), True
