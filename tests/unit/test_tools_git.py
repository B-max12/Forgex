import subprocess
from pathlib import Path

from forgex.tools.git import (
    current_branch, git_checkpoint, git_diff, git_log, git_status, has_git_repo,
)


def git_repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "checkout", "-q", "-b", "main"], cwd=tmp_path, check=True, capture_output=True)
    return tmp_path


def test_checkpoint_commits_work(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))  # no user git identity
    (tmp_path / "home").mkdir(exist_ok=True)
    git_repo(tmp_path)
    (tmp_path / "a.txt").write_text("v1", encoding="utf-8")
    commit = git_checkpoint(tmp_path, "initial work")
    assert commit and commit in git_log(tmp_path)
    assert has_git_repo(tmp_path)
    # second checkpoint with no changes returns same HEAD, no new commit
    assert git_checkpoint(tmp_path, "noop") == commit


def test_status_and_diff(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir(exist_ok=True)
    git_repo(tmp_path)
    (tmp_path / "a.txt").write_text("v1", encoding="utf-8")
    git_checkpoint(tmp_path, "initial")
    (tmp_path / "a.txt").write_text("v2", encoding="utf-8")
    assert "a.txt" in git_status(tmp_path)
    assert "+v2" in git_diff(tmp_path)
    assert current_branch(tmp_path) == "main"


def test_checkpoint_without_repo_returns_none(tmp_path):
    assert git_checkpoint(tmp_path, "x") is None
    assert git_status(tmp_path) == "not a git repository"


def test_commit_uses_user_identity_when_present(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir(exist_ok=True)
    git_repo(tmp_path)
    subprocess.run(["git", "config", "user.email", "dev@example.com"], cwd=tmp_path,
                   check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Dev"], cwd=tmp_path,
                   check=True, capture_output=True)
    (tmp_path / "b.txt").write_text("x", encoding="utf-8")
    git_checkpoint(tmp_path, "with identity")
    log = subprocess.run(["git", "log", "-1", "--format=%an"], cwd=tmp_path,
                         capture_output=True, text=True, check=True).stdout.strip()
    assert log == "Dev"
