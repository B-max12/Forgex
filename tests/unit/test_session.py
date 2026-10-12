from pathlib import Path

from forgex.cli.session import Session
from forgex.project import initialize_project


def test_session_unattached(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    session = Session()
    assert session.is_attached is False
    assert session.project_name == "unattached"
    assert session.get_state() is None
    assert session.get_tasks() == []


def test_session_attached(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    initialize_project(tmp_path)
    session = Session()
    assert session.is_attached is True
    assert session.project_name == tmp_path.name
    state = session.get_state()
    assert state is not None
    assert state.project_path == str(tmp_path)


def test_session_change_directory(tmp_path: Path, monkeypatch):
    d1 = tmp_path / "proj1"
    d2 = tmp_path / "proj2"
    d1.mkdir()
    d2.mkdir()
    initialize_project(d2)

    monkeypatch.chdir(d1)
    session = Session()
    assert session.is_attached is False

    ok = session.change_directory(d2)
    assert ok is True
    assert session.is_attached is True
    assert session.project_name == "proj2"


def test_session_lazy_router(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    session = Session()
    assert session._router is None
    router = session.get_router()
    assert router is not None
    assert session._router is router
