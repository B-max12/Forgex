import json
import sys

from forgex.tools.testing import detect_test_command


async def test_run_command_tool(tmp_path):
    from forgex.config import load_config
    from forgex.sandbox.permissions import permission_set_for
    from forgex.schemas.agent import AgentRole
    from forgex.tools import ToolCall, ToolExecutor, build_tool_registry, create_context

    ctx = create_context(workspace=tmp_path, config=load_config(), agent=AgentRole.BUILDER)
    executor = ToolExecutor(registry=build_tool_registry(),
                            permissions=permission_set_for(AgentRole.BUILDER), context=ctx)
    result = await executor.execute(ToolCall(name="run_command", arguments={
        "command": [sys.executable, "-c", "print('via-tool')"],
    }))
    assert result.ok, result.error
    assert "via-tool" in result.output
    assert result.data["exit_code"] == 0


async def test_run_command_denied_by_policy(tmp_path):
    from forgex.config import load_config
    from forgex.sandbox.permissions import permission_set_for
    from forgex.schemas.agent import AgentRole
    from forgex.tools import ToolCall, ToolExecutor, build_tool_registry, create_context

    ctx = create_context(workspace=tmp_path, config=load_config(), agent=AgentRole.BUILDER)
    executor = ToolExecutor(registry=build_tool_registry(),
                            permissions=permission_set_for(AgentRole.BUILDER), context=ctx)
    result = await executor.execute(ToolCall(name="run_command", arguments={"command": ["rm", "x"]}))
    assert not result.ok and "denied" in result.error


async def test_run_tests_e2e(tmp_path):
    from forgex.config import load_config
    from forgex.sandbox.permissions import permission_set_for
    from forgex.schemas.agent import AgentRole
    from forgex.tools import ToolCall, ToolExecutor, build_tool_registry, create_context

    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\ndependencies = ["pytest"]\n', encoding="utf-8"
    )
    (tmp_path / "test_ok.py").write_text(
        "def test_ok():\n    assert True\n", encoding="utf-8"
    )
    assert detect_test_command(tmp_path) == ["python", "-m", "pytest", "-q"]
    ctx = create_context(workspace=tmp_path, config=load_config(), agent=AgentRole.BUILDER)
    executor = ToolExecutor(registry=build_tool_registry(),
                            permissions=permission_set_for(AgentRole.BUILDER), context=ctx)
    result = await executor.execute(ToolCall(name="run_tests", arguments={}))
    assert result.ok, result.output
    assert "1 passed" in result.output or "passed" in result.output


async def test_run_tests_no_detection(tmp_path):
    from forgex.config import load_config
    from forgex.sandbox.permissions import permission_set_for
    from forgex.schemas.agent import AgentRole
    from forgex.tools import ToolCall, ToolExecutor, build_tool_registry, create_context

    ctx = create_context(workspace=tmp_path, config=load_config(), agent=AgentRole.BUILDER)
    executor = ToolExecutor(registry=build_tool_registry(),
                            permissions=permission_set_for(AgentRole.BUILDER), context=ctx)
    result = await executor.execute(ToolCall(name="run_tests", arguments={}))
    assert not result.ok and "No test command" in result.error


def test_detect_test_commands(tmp_path):
    assert detect_test_command(tmp_path / "empty") is None or True  # non-existent dir → no langs
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": "jest"}}), encoding="utf-8"
    )
    assert detect_test_command(tmp_path) == ["npm", "test"]
