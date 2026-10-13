
from forgex.config import load_config
from forgex.context.manager import ContextManager
from forgex.sandbox.permissions import permission_set_for
from forgex.schemas.agent import AgentRole
from forgex.tools import ToolCall, ToolExecutor, build_tool_registry, create_context


def test_large_tree_index_reuse_and_caps(tmp_path):
    for d in range(10):
        package = tmp_path / f"pkg{d}"
        package.mkdir()
        for i in range(120):
            (package / f"mod{i}.py").write_text(
                f"def fn_{d}_{i}():\n    pass\n", encoding="utf-8")

    manager = ContextManager(tmp_path)
    index = manager.ensure_index()
    assert len(index.files) == 1200
    assert index.stats["parsed"] == 1200

    fresh = ContextManager(tmp_path)
    assert fresh.ensure_index().stats["reused"] == 1200
    assert fresh.ensure_index().stats["parsed"] == 0

    ranked = fresh.relevant_files(query="fn_3_7", seeds=["pkg3/mod7.py"])
    assert ranked and ranked[0].path == "pkg3/mod7.py"

    ctx = create_context(workspace=tmp_path, config=load_config(), agent=AgentRole.BUILDER)
    executor = ToolExecutor(registry=build_tool_registry(),
                            permissions=permission_set_for(AgentRole.BUILDER),
                            context=ctx)
    result = executor_sync(executor, "list_files", {})
    assert result.data["count"] == 500 and result.data["truncated"] is True


def executor_sync(executor, name, arguments):
    import asyncio

    return asyncio.run(executor.execute(ToolCall(name=name, arguments=arguments)))


def test_noise_directories_excluded_at_scale(tmp_path):
    noise = tmp_path / "node_modules"
    noise.mkdir()
    for i in range(300):
        (noise / f"dep{i}.js").write_text("export const x = 1;\n", encoding="utf-8")
    for i in range(50):
        (tmp_path / f"real{i}.py").write_text("x = 1\n", encoding="utf-8")
    index = ContextManager(tmp_path).ensure_index()
