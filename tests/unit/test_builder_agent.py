from __future__ import annotations

import json
from typing import Any, cast

from forgex.agents.builder import BuilderAgent, execute_task
from forgex.config import load_config
from forgex.models.base import ModelResponse, ToolCall
from forgex.models.capabilities import ModelCapabilities
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


def tool_call_response(name, arguments, call_id="call_1"):
    return ModelResponse(
        content=None,
        tool_calls=[ToolCall(id=call_id, name=name, arguments=arguments)],
    )


def final_response(payload: dict) -> ModelResponse:
    return ModelResponse(content=json.dumps(payload), tool_calls=[])


async def test_builder_executes_task_and_records_events(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    initialize_project(ws)
    with open_stores(ws) as stores:
        state = stores.state.load()
        assert state is not None
        task = Task(id="TASK-001", description="create demo file", acceptance_criteria=["exists"])
        stores.save_tasks([task], project_id=state.project_id)

        router = FakeRouter([
            tool_call_response("write_file", json.dumps({"path": "demo.py", "content": "print(1)"})),
            final_response({"status": "completed", "summary": "done", "created_files": ["demo.py"], "modified_files": [], "tests_written": []}),
        ])
        ctx = create_context(ws, load_config(ws), agent=AgentRole.BUILDER, events=stores.recorder)
        tools = ToolExecutor(build_tool_registry(), permission_set_for(AgentRole.BUILDER), ctx)
        builder = BuilderAgent(router=cast(Any, router), tools=tools, events=stores.recorder)

        res = await execute_task(stores=stores, task=task, config=load_config(ws), builder=builder)
        assert res.status == "completed"
        assert (ws / "demo.py").exists()


async def test_builder_json_protocol_mode(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    initialize_project(ws)
    with open_stores(ws) as stores:
        state = stores.state.load()
        assert state is not None
        task = Task(id="TASK-001", description="create demo file", acceptance_criteria=["exists"])
        stores.save_tasks([task], project_id=state.project_id)

        router = FakeRouter([
            ModelResponse(content=json.dumps({
                "action": "tool",
                "tool": "write_file",
                "arguments": {"path": "proto.py", "content": "print('protocol')"},
            })),
            ModelResponse(content=json.dumps({
                "action": "done",
                "result": {"status": "completed", "summary": "done via protocol", "created_files": ["proto.py"], "modified_files": [], "tests_written": []},
            })),
        ], supports_tools=False)
        ctx = create_context(ws, load_config(ws), agent=AgentRole.BUILDER, events=stores.recorder)
        tools = ToolExecutor(build_tool_registry(), permission_set_for(AgentRole.BUILDER), ctx)
        builder = BuilderAgent(router=cast(Any, router), tools=tools, events=stores.recorder)

        res = await execute_task(stores=stores, task=task, config=load_config(ws), builder=builder)
        assert res.status == "completed"
        assert (ws / "proto.py").exists()

