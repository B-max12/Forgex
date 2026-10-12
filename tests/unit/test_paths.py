from __future__ import annotations

import sys
from pathlib import Path

import pytest

from forgex.utils.paths import PathViolationError, resolve_in_workspace


def test_relative_path_inside(tmp_path: Path):
    assert resolve_in_workspace(tmp_path, "src/main.py") == (tmp_path / "src" / "main.py").resolve()


def test_dotdot_still_inside_ok(tmp_path: Path):
    assert resolve_in_workspace(tmp_path, "src/../README.md") == (tmp_path / "README.md").resolve()


def test_dotdot_escape_rejected(tmp_path: Path):
    with pytest.raises(PathViolationError):
        resolve_in_workspace(tmp_path, "../outside.txt")


def test_absolute_outside_rejected(tmp_path: Path):
    with pytest.raises(PathViolationError):
        resolve_in_workspace(tmp_path, "/etc/passwd" if sys.platform != "win32" else "C:/Windows/system32")


def test_absolute_inside_allowed(tmp_path: Path):
    p = tmp_path / "a.txt"
    p.write_text("x")
    assert resolve_in_workspace(tmp_path, str(p)) == p.resolve()


def test_workspace_root_itself_allowed(tmp_path: Path):
    assert resolve_in_workspace(tmp_path, ".") == tmp_path.resolve()


@pytest.mark.skipif(sys.platform == "win32", reason="symlink creation needs privileges on Windows")
def test_symlink_escape_rejected(tmp_path: Path):
    outside = tmp_path.parent / "outside-dir"
    outside.mkdir(exist_ok=True)
    link = tmp_path / "link"
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(PathViolationError):
        resolve_in_workspace(tmp_path, "link/secret.txt")
