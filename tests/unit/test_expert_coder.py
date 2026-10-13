from __future__ import annotations

import json
import subprocess

from forgex.agents.expert_coder import ExpertCoderAgent, review_work
from forgex.config import load_config
from forgex.models.base import ModelResponse
from forgex.models.capabilities import ModelCapabilities
from forgex.orchestration.checkpoints import create_checkpoint
from forgex.orchestration.stores import open_stores
from forgex.project import initialize_project
from forgex.sandbox.permissions import permission_set_for
from forgex.schemas.agent import AgentRole
from forgex.schemas.task import Task
from forgex.tools import ToolExecutor, build_tool_registry, create_context


class FakeRouter:
    def __init__(self, replies, *, supports_tools=True):
        self.replies = list(replies)
        self.calls = []
        self._caps = ModelCapabilities(model="fake", supports_tools=supports_tools)

    def capabilities_for(self, agent):
        return self._caps

    async def generate(self, agent, *, messages, system=None, tools=None,
                       tool_choice=None, response_format=None, temperature=None, **kw):
        self.calls.append({"messages": messages, "tools": tools})
        assert self.replies, "FakeRouter out of scripted replies"
        return self.replies.pop(0)

    async def aclose(self):
        return None


def final_response(payload: dict) -> ModelResponse:
    return ModelResponse(content=json.dumps(payload), tool_calls=[])


def make_workspace(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.chdir(ws)
    subprocess.run(["git", "init"], cwd=ws, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=ws, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=ws, check=True)
    initialize_project(ws)
    return ws


def make_coder(ws, replies):
    router = FakeRouter(replies)
    ctx = create_context(workspace=ws, config=load_config(ws), agent=AgentRole.EXPERT_CODER)
    tools = ToolExecutor(registry=build_tool_registry(), permissions=permission_set_for(AgentRole.EXPERT_CODER), context=ctx)
    coder = ExpertCoderAgent(router=router, tools=tools)
    coder._router = router
    return coder

async def test_review_work_committed_range(tmp_path, monkeypatch):
    ws = make_workspace(tmp_path, monkeypatch)
    (ws / "app.py").write_text("x = 1\n", encoding="utf-8")
    with open_stores(ws) as stores:
        state = stores.state.load()
        stores.save_tasks([Task(id="TASK-001", description="write app")],
                          project_id=state.project_id)
        create_checkpoint("pre-TASK-001", stores=stores)
    (ws / "app.py").write_text("x = 2\n", encoding="utf-8")
    with open_stores(ws) as stores:
        create_checkpoint("post-task", stores=stores)  # tree is now clean

    coder = make_coder(ws, [
        final_response({"status": "completed", "summary": "reviewed committed work",
                        "changed_files": [], "improvements": [],
                        "issues_found": [], "unfixed_issues": []}),
    ])
    with open_stores(ws) as stores:
        result = await review_work(stores=stores, config=load_config(),
                                   task_id="TASK-001", coder=coder)

    assert result is not None and result.status == "completed"
    # the diff actually reached the model
    user_message = coder._router.calls[0]["messages"][0].content
    assert "+x = 2" in user_message


async def test_review_work_checkpoint_and_state_update(tmp_path, monkeypatch):
    ws = make_workspace(tmp_path, monkeypatch)
    (ws / "m.py").write_text("m = 1\n", encoding="utf-8")
    coder = make_coder(ws, [
        final_response({"status": "completed", "summary": "tightened",
                        "changed_files": ["m.py"], "improvements": ["removed dead code"],
                        "issues_found": ["dead code"], "unfixed_issues": []}),
    ])
    with open_stores(ws) as stores:
        result = await review_work(stores=stores, config=load_config(), coder=coder)
    assert result is not None
    with open_stores(ws) as stores:
        state = stores.state.load()
        assert "m.py" in state.changed_files
        project_id = state.project_id
        labels = [c.label for c in stores.checkpoints.list(project_id, limit=10)]
    assert any(label.startswith("pre-review") for label in labels)
