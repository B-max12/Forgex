from pathlib import Path

from typer.testing import CliRunner

from forgex.cli.app import app
from forgex.orchestration.stores import open_stores
from forgex.schemas.agent import BuilderResult
from forgex.schemas.plan import ArchitecturePlan
from forgex.schemas.task import Task

runner = CliRunner()


def seed_plan(tmp_path: Path):
    runner.invoke(app, ["init"])
    with open_stores(tmp_path) as stores:
        state = stores.state.load()
        state.architecture_plan = ArchitecturePlan(goal="demo")
        stores.save_state(state)
        stores.save_tasks(
            [
                Task(id="TASK-001", description="First"),
                Task(id="TASK-002", description="Second", depends_on=["TASK-001"]),
            ],
            project_id=state.project_id,
        )


class FakeBuilder:
    def __init__(self, result=None):
        self.result = result or BuilderResult(
            status="completed", summary="did the thing",
            changed_files=["out/TASK-001.txt"],
        )
        self.executed = []

    async def execute(self, task, *, plan, research=None):
        self.executed.append(task.id)
        return self.result

    async def aclose(self):
        return None


def install_fake(monkeypatch, builder=None):
    fake = builder or FakeBuilder()
    monkeypatch.setattr("forgex.agents.builder.build_builder",
                        lambda **kwargs: fake)
    return fake
