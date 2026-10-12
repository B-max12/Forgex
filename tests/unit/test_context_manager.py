import json
from pathlib import Path

from typer.testing import CliRunner

from forgex.cli.app import app
from forgex.context.manager import ContextManager

runner = CliRunner()


def write(tmp_path: Path, rel: str, content: str) -> None:
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_build_context_respects_budget(tmp_path):
    write(tmp_path, "src/big.py", "import os\n\ndef a():\n    pass\n" + "# padding\n" * 400)
    write(tmp_path, "src/small.py", "def small():\n    pass\n")
    manager = ContextManager(tmp_path)
    bundle = manager.build_context(query="small helper", seeds=["src/small.py"],
                                   budget=2000, max_files=4)
    rendered = bundle.render()
    assert "--- src/small.py ---" in rendered
    total = sum(len(f.content) for f in bundle.files)
    assert total <= 2000 + 200  # budget + small slack for markers
    assert bundle.stats["index_files"] == 2


def test_symbol_map(tmp_path):
    write(tmp_path, "src/app.py", "class Engine:\n    def run(self):\n        pass\n")
    write(tmp_path, "src/other.py", "def standalone():\n    pass\n")
    mapping = ContextManager(tmp_path).symbol_map()
    assert "src/app.py: class Engine, Engine.run" in mapping
    assert "standalone" in mapping


def test_cache_persisted_and_reused(tmp_path):
    write(tmp_path, "a.py", "def a(): pass\n")
    manager = ContextManager(tmp_path)
    manager.ensure_index()
    cache = tmp_path / ".forgex" / "cache" / "context-index.json"
    assert cache.is_file()
    fresh = ContextManager(tmp_path)
    assert fresh.ensure_index().stats["reused"] == 1
    assert fresh.ensure_index().stats["parsed"] == 0


def test_cli_context_stats_and_search(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["init"])
    write(tmp_path, "src/app.py", "class Engine:\n    def run(self):\n        pass\n")
    stats = runner.invoke(app, ["context", "stats", "--json"])
    assert stats.exit_code == 0, stats.output
    payload = json.loads(stats.output)
    assert payload["files"] >= 1 and payload["symbols"] >= 1

    search = runner.invoke(app, ["context", "search", "--query", "engine run", "--json"])
    assert search.exit_code == 0, search.output
    results = json.loads(search.output)["results"]
    assert results and results[0]["path"] == "src/app.py"
    assert results[0]["reasons"]
