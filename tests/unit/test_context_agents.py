import json
from pathlib import Path

from forgex.agents.builder import BuilderAgent
from forgex.agents.expert_coder import ExpertCoderAgent
from forgex.config import load_config
from forgex.models.base import ModelResponse
from forgex.models.capabilities import ModelCapabilities
from forgex.sandbox.permissions import permission_set_for
from forgex.schemas.agent import AgentRole
from forgex.schemas.plan import ArchitecturePlan
from forgex.schemas.task import Task
from forgex.tools import ToolExecutor, build_tool_registry, create_context


class FakeRouter:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def capabilities_for(self, agent):
        return ModelCapabilities(model="fake", supports_tools=True)

    async def generate(self, agent, *, messages, system=None, **kw):
        self.calls.append({"messages": messages})
        return ModelResponse(content=self.reply, model="fake", provider="fake")

    async def aclose(self):
        return None


def write(tmp_path: Path, rel: str, content: str) -> None:
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def make_tools(tmp_path, role):
    ctx = create_context(workspace=tmp_path, config=load_config(), agent=role)
    return ToolExecutor(registry=build_tool_registry(),
                        permissions=permission_set_for(role), context=ctx)


async def test_builder_instruction_includes_importer(tmp_path):
    write(tmp_path, "src/helpers.py", "def tool():\n    return 42\n")
    write(tmp_path, "src/api.py", "from .helpers import tool\n\nclass Api:\n    pass\n")
    router = FakeRouter(json.dumps({"status": "completed", "summary": "ok",
                                    "changed_files": ["src/helpers.py"]}))
    agent = BuilderAgent(router=router, tools=make_tools(tmp_path, AgentRole.BUILDER))
    task = Task(id="TASK-001", description="extend helpers tool",
                files=["src/helpers.py"])
    await agent.execute(task, plan=ArchitecturePlan(goal="demo"))

    instruction = router.calls[0]["messages"][0].content
    assert "src/helpers.py" in instruction          # planned seed
    assert "class Api" in instruction               # importer pulled in (impact context)


async def test_expert_coder_review_includes_importers(tmp_path):
    write(tmp_path, "src/helpers.py", "def tool():\n    return 43\n")
    write(tmp_path, "src/api.py", "from .helpers import tool\n\nclass Api:\n    pass\n")
    router = FakeRouter(json.dumps({"status": "completed", "summary": "clean",
                                    "changed_files": []}))
    agent = ExpertCoderAgent(router=router,
                             tools=make_tools(tmp_path, AgentRole.EXPERT_CODER))
    await agent.review(diff="+def tool():", changed_files=["src/helpers.py"])

    instruction = router.calls[0]["messages"][0].content
