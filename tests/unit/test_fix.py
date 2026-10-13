import json
from pathlib import Path

from typer.testing import CliRunner

from forgex.cli.app import app
from forgex.config import load_config
from forgex.orchestration.engine import BuildEngine
from forgex.orchestration.state import StateStore
from forgex.orchestration.stores import open_stores
from tests.unit.test_engine import (
    FAILING_TEST,
    PASSING_TEST,
    PLAN,
    FakeBuilder,
    FakeCoder,
    FakePlanner,
    FakeSupervisor,
    seed,
)

runner = CliRunner()


async def run_fix(tmp_path, *, coder, supervisor=None):
    agents = {"planner": FakePlanner(), "builder": FakeBuilder(),
              "coder": coder, "supervisor": supervisor or FakeSupervisor()}
    with open_stores(tmp_path) as stores:
        engine = BuildEngine(stores=stores, config=load_config(), agents=agents)
        return await engine.fix()


async def test_fix_repairs_until_green(tmp_path, monkeypatch):
    seed(tmp_path, monkeypatch, plan_tasks=[PLAN[0]], test_body=FAILING_TEST)

    def fix():
        (tmp_path / "test_x.py").write_text(PASSING_TEST, encoding="utf-8")

    result = await run_fix(tmp_path, coder=FakeCoder(fix=fix))
    assert result.status == "completed"
    assert result.iterations == 1
    assert StateStore(tmp_path).load().status.value == "completed"


async def test_fix_resets_iteration_budget(tmp_path, monkeypatch):
    seed(tmp_path, monkeypatch, plan_tasks=[PLAN[0]])  # passing suite
    with open_stores(tmp_path) as stores:  # simulate an exhausted prior build
        state = stores.state.load()
        state.iteration = 5
        stores.save_state(state)
    result = await run_fix(tmp_path, coder=FakeCoder())
    assert result.status == "completed"   # not blocked by the old budget
    assert result.iterations == 0


def test_cli_fix_end_to_end(tmp_path: Path, monkeypatch):
    seed(tmp_path, monkeypatch, plan_tasks=[PLAN[0]])
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("forgex.orchestration.engine.build_planner",
                        lambda **kw: FakePlanner())
    monkeypatch.setattr("forgex.orchestration.engine.build_builder",
                        lambda **kw: FakeBuilder())
    monkeypatch.setattr("forgex.orchestration.engine.build_coder",
                        lambda **kw: FakeCoder())
    monkeypatch.setattr("forgex.orchestration.engine.build_supervisor",
                        lambda **kw: FakeSupervisor())
    result = runner.invoke(app, ["fix", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["status"] == "completed"
