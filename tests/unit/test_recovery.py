
import pytest

from forgex.orchestration.state import StateStore, TaskStore
from forgex.schemas.agent import BuilderResult
from tests.unit.test_engine import FakeBuilder, FakeSupervisor, run_engine, seed


class ExplodingBuilder(FakeBuilder):
    async def execute(self, task, *, plan, research=None):
        self.ran.append(task.id)
        if task.id == "TASK-002":
            raise RuntimeError("agent internal bug")
        return BuilderResult(status="completed", summary=f"built {task.id}",
                             changed_files=[f"out_{task.id}.txt"])


async def test_engine_survives_unexpected_builder_crash(tmp_path, monkeypatch):
    seed(tmp_path, monkeypatch)
    result = await run_engine(tmp_path, builder=ExplodingBuilder(), max_iterations=1)
    assert result.status == "failed"
    assert any("TASK-002" in item for item in result.remaining_tasks)
    tasks = {t.id: t for t in TaskStore(tmp_path).load()}
    assert tasks["TASK-002"].status.value == "failed"
    assert "builder error" in (tasks["TASK-002"].result or "")
    state = StateStore(tmp_path).load()
    assert any(e.kind == "RuntimeError" for e in state.errors)


class InterruptingSupervisor(FakeSupervisor):
    def __init__(self):
        super().__init__()
        self.calls = 0

    async def audit(self, **kwargs):
        self.calls += 1
        raise KeyboardInterrupt


async def test_engine_interrupted_leaves_clean_state(tmp_path, monkeypatch):
    seed(tmp_path, monkeypatch)
    with pytest.raises(KeyboardInterrupt):
        await run_engine(tmp_path, supervisor=InterruptingSupervisor())
    state = StateStore(tmp_path).load()
    assert state is not None
