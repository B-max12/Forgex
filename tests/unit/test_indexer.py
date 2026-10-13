from pathlib import Path

from forgex.context.dependency_graph import DependencyGraph
from forgex.context.indexer import IndexData, build


def write(tmp_path: Path, rel: str, content: str) -> None:
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_python_symbols_and_imports(tmp_path):
    write(tmp_path, "src/app.py",
          "import os\nfrom . import models\nfrom services import auth\n\n"
          "class UserService:\n    def login(self):\n        pass\n\n"
          "    def logout(self):\n        pass\n\n\ndef helper():\n    pass\n")
    index = build(tmp_path)
    entry = index.files["src/app.py"]
    names = {s.name for s in entry.symbols}
    assert {"UserService", "UserService.login", "UserService.logout", "helper"} <= names
    assert set(entry.imports) >= {"os", ".models", "services"}


def test_syntax_error_tolerated(tmp_path):
    write(tmp_path, "broken.py", "def f(:\n")
    index = build(tmp_path)
    assert index.files["broken.py"].symbols == []


def test_js_imports_and_exports(tmp_path):
    write(tmp_path, "app.js",
          "import { tool } from './utils';\nconst x = require('fs');\n"
          "export function run() {}\nexport class Engine {}\n")
    index = build(tmp_path)
    entry = index.files["app.js"]
    assert "./utils" in entry.imports and "fs" in entry.imports
    assert {"run", "Engine"} <= {s.name for s in entry.symbols}


def test_secret_and_noise_files_skipped(tmp_path):
    write(tmp_path, ".env", "SECRET=1")
    write(tmp_path, "node_modules/pkg.js", "export const x = 1;")
    write(tmp_path, "real.py", "x = 1\n")
    index = build(tmp_path)
    assert set(index.files) == {"real.py"}


def test_cache_invalidation_by_size(tmp_path):
    write(tmp_path, "a.py", "def a(): pass\n")
    write(tmp_path, "b.py", "def b(): pass\n")
    first = build(tmp_path)
    assert first.stats["parsed"] == 2

    cached = IndexData.model_validate_json(first.model_dump_json())
    write(tmp_path, "a.py", "def a():\n    return 42\n")  # changed (size differs)
    second = build(tmp_path, cached)
    assert second.stats["parsed"] == 1
    assert second.stats["reused"] == 1
    assert second.files["a.py"].symbols[0].name == "a"


def test_deleted_files_pruned(tmp_path):
    write(tmp_path, "gone.py", "x = 1\n")
    first = build(tmp_path)
    (tmp_path / "gone.py").unlink()
    second = build(tmp_path, first)
    assert "gone.py" not in second.files
    assert second.stats["pruned"] == 1


def test_graph_python_resolution(tmp_path):
    write(tmp_path, "src/app.py", "from .models import User\nfrom utils.helpers import tool\n")
    write(tmp_path, "src/models.py", "class User: pass\n")
    write(tmp_path, "utils/helpers.py", "def tool(): pass\n")
    graph = DependencyGraph(build(tmp_path))
    assert set(graph.imports_of("src/app.py")) == {"src/models.py", "utils/helpers.py"}
    assert graph.importers_of("src/models.py") == {"src/app.py": 1}


def test_graph_transitive_importers(tmp_path):
    write(tmp_path, "a.py", "import b\n")
    write(tmp_path, "b.py", "import c\n")
    write(tmp_path, "c.py", "x = 1\n")
    graph = DependencyGraph(build(tmp_path))
    assert graph.importers_of("c.py", max_depth=2) == {"b.py": 1, "a.py": 2}


def test_graph_js_relative_and_external(tmp_path):
    write(tmp_path, "src/app.js", "import { t } from './utils';\nimport React from 'react';\n")
    write(tmp_path, "src/utils.js", "export const t = 1;\n")
    graph = DependencyGraph(build(tmp_path))
    assert graph.imports_of("src/app.js") == {"src/utils.js": 1}
    assert graph.importers_of("src/utils.js") == {"src/app.js": 1}
