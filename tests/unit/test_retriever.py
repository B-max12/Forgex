from pathlib import Path

from forgex.context.chunker import chunk_python, select_chunks
from forgex.context.dependency_graph import DependencyGraph
from forgex.context.indexer import build
from forgex.context.retriever import query_terms, score_files


def write(tmp_path: Path, rel: str, content: str) -> None:
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_query_terms():
    terms = query_terms("Implement user_service loginHandler for the API")
    assert "user" in terms and "service" in terms and "login" in terms and "handler" in terms
    assert "the" not in terms and "for" not in terms


def test_chunker_selects_matching_symbols():
    source = (
        "import os\n\n"
        "def login():\n    return 'in'\n\n\n"
        "def logout():\n    return 'out'\n"
    )
    chunks = chunk_python(source)
    names = {c.name for c in chunks}
    assert "module-head" in names and "login" in names and "logout" in names
    text, truncated = select_chunks(chunks, {"login"}, max_chars=60)
    assert truncated is True
    assert "import os" in text and "def login" in text


def test_seeds_importers_and_tests_ranked(tmp_path):
    write(tmp_path, "src/auth.py", "from .models import User\n\n"
                                   "class AuthService:\n    def login(self):\n        pass\n")
    write(tmp_path, "src/models.py", "class User:\n    pass\n")
    write(tmp_path, "src/app.py", "from .auth import AuthService\n")
    write(tmp_path, "tests/test_auth.py", "from src.auth import AuthService\n")
    write(tmp_path, "docs/readme.md", "# docs\n")
    index = build(tmp_path)
    graph = DependencyGraph(index)
    ranked = score_files(index=index, graph=graph,
                         query="user login authentication", seeds=["src/auth.py"])
    paths = [s.path for s in ranked]
    assert paths[0] == "src/auth.py"                      # seed
    assert "src/app.py" in paths[:3]                       # importer
    assert "tests/test_auth.py" in paths                   # related test
    seed = ranked[0]
    assert any("seed" in r for r in seed.reasons)
    app = next(s for s in ranked if s.path == "src/app.py")
    assert any("imports seed" in r for r in app.reasons)


def test_symbol_match_without_seeds(tmp_path):
    write(tmp_path, "billing.py", "def process_payment():\n    pass\n")
    write(tmp_path, "other.py", "x = 1\n")
    index = build(tmp_path)
    ranked = score_files(index=index, graph=DependencyGraph(index),
                         query="payment processing", seeds=[])
    assert ranked and ranked[0].path == "billing.py"
    assert any("symbol" in r for r in ranked[0].reasons)
