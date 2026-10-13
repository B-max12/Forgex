from pathlib import Path

from forgex.config import load_config
from forgex.sandbox.permissions import permission_set_for
from forgex.schemas.agent import AgentRole
from forgex.tools import ToolCall, ToolExecutor, build_tool_registry, create_context


def make_executor(tmp_path: Path, *, agent=AgentRole.BUILDER, approval=None, events=None):
    ctx = create_context(workspace=tmp_path, config=load_config(),
                         events=events, approval=approval, agent=agent)
    return ToolExecutor(registry=build_tool_registry(),
                        permissions=permission_set_for(agent), context=ctx)


async def run(tmp_path, name, args, *, agent=AgentRole.BUILDER, approval=None, events=None):
    return await make_executor(tmp_path, agent=agent, approval=approval, events=events).execute(
        ToolCall(name=name, arguments=args)
    )


async def test_write_then_read_roundtrip(tmp_path):
    w = await run(tmp_path, "write_file", {"path": "src/app.py", "content": "print('hi')"})
    assert w.ok, w.error
    r = await run(tmp_path, "read_file", {"path": "src/app.py"})
    assert r.ok and "print('hi')" in r.output


async def test_read_missing_file_fails(tmp_path):
    r = await run(tmp_path, "read_file", {"path": "nope.txt"})
    assert not r.ok and "not found" in r.error
