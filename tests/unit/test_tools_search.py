from pathlib import Path

import forgex.tools.search as search_mod
from forgex.tools import ToolCall, ToolExecutor, build_tool_registry, create_context
from forgex.config import load_config
from forgex.schemas.agent import AgentRole
from forgex.sandbox.permissions import permission_set_for


async def run(tmp_path, name, args):
    ctx = create_context(workspace=tmp_path, config=load_config(), agent=AgentRole.BUILDER)
    executor = ToolExecutor(registry=build_tool_registry(),
                            permissions=permission_set_for(AgentRole.BUILDER), context=ctx)
    return await executor.execute(ToolCall(name=name, arguments=args))


async def test_search_code_python_engine(tmp_path, monkeypatch):
    monkeypatch.setattr(search_mod, "_rg_available", lambda: False)
    (tmp_path / "app.py").write_text("def find_me():\n    return 42\n", encoding="utf-8")
    r = await run(tmp_path, "search_code", {"query": "find_me"})
    assert r.ok and "app.py:1" in r.output


async def test_search_code_skips_noise_and_secrets(tmp_path, monkeypatch):
    monkeypatch.setattr(search_mod, "_rg_available", lambda: False)
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "j.js").write_text("find_me", encoding="utf-8")
    (tmp_path / ".env").write_text("find_me=gsk-xyz", encoding="utf-8")
    (tmp_path / "src.py").write_text("find_me", encoding="utf-8")
    r = await run(tmp_path, "search_code", {"query": "find_me"})
    assert "src.py" in r.output
    assert "j.js" not in r.output and "gsk-xyz" not in r.output


async def test_search_code_regex(tmp_path, monkeypatch):
    monkeypatch.setattr(search_mod, "_rg_available", lambda: False)
    (tmp_path / "a.py").write_text("value = 123\n", encoding="utf-8")
    r = await run(tmp_path, "search_code", {"query": r"VA*LUE\s*=", "regex": True})
    assert r.ok and "a.py:1" in r.output


async def test_search_files_glob(tmp_path):
    (tmp_path / "one.py").write_text("x", encoding="utf-8")
    (tmp_path / "two.txt").write_text("x", encoding="utf-8")
    r = await run(tmp_path, "search_files", {"pattern": "*.py"})
    assert r.ok and "one.py" in r.output and "two.txt" not in r.output
