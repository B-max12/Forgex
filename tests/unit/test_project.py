from __future__ import annotations

from pathlib import Path

from forgex.project import detect_project


def test_empty_dir(tmp_path: Path):
    det = detect_project(tmp_path)
    assert det.languages == []
    assert det.has_git is False


def test_python_fastapi(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies = ["fastapi>=0.111", "sqlalchemy"]\n'
    )
    (tmp_path / "requirements.txt").write_text("pytest\n")
    det = detect_project(tmp_path)
    assert "Python" in det.languages
    assert "FastAPI" in det.frameworks
    assert "SQLAlchemy" in det.frameworks
    assert "Pytest" in det.test_frameworks
    assert "pip" in det.package_managers


def test_node_pnpm(tmp_path: Path):
    (tmp_path / "package.json").write_text(
        '{"dependencies": {"express": "^4"}, "devDependencies": {"jest": "^29"}}'
    )
    (tmp_path / "pnpm-lock.yaml").write_text("")
    det = detect_project(tmp_path)
    assert "JavaScript" in det.languages
    assert "Express" in det.frameworks
    assert "Jest" in det.test_frameworks
    assert "pnpm" in det.package_managers


def test_rust_and_go(tmp_path: Path):
    (tmp_path / "Cargo.toml").write_text("[package]\nname = 'x'\n")
    det = detect_project(tmp_path)
    assert "Rust" in det.languages and "cargo" in det.package_managers

    (tmp_path / "go.mod").write_text("module example.com/x\n\ngo 1.22\n")
    det = detect_project(tmp_path)
    assert "Go" in det.languages
