from pathlib import Path

from forgex.tools import ToolCall, ToolExecutor, build_tool_registry, create_context
from forgex.config import load_config
from forgex.schemas.agent import AgentRole
from forgex.sandbox.permissions import permission_set_for


async def inspect(tmp_path: Path):
    ctx = create_context(workspace=tmp_path, config=load_config(), agent=AgentRole.BUILDER)
    executor = ToolExecutor(registry=build_tool_registry(),
                            permissions=permission_set_for(AgentRole.BUILDER), context=ctx)
    result = await executor.execute(ToolCall(name="inspect_dependencies", arguments={}))
    assert result.ok, result.error
    return result.data


async def test_python_and_node_manifests(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies = ["fastapi>=0.111", "pydantic"]\n'
        '[project.optional-dependencies]\ndev = ["pytest"]\n',
        encoding="utf-8",
    )
    (tmp_path / "requirements.txt").write_text("httpx==0.27\n# comment\n", encoding="utf-8")
    (tmp_path / "package.json").write_text(
        '{"dependencies": {"express": "^4"}, "devDependencies": {"jest": "^29"}}',
        encoding="utf-8",
    )
    data = await inspect(tmp_path)
    names = {d["name"] for d in data["dependencies"]}
    assert {"fastapi", "pydantic", "pytest", "httpx", "express", "jest"} <= names
    dev = {d["name"] for d in data["dependencies"] if d["dev"]}
    assert {"pytest", "jest"} <= dev


async def test_cargo_and_go_manifests(tmp_path):
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "x"\n[dependencies]\nserde = "1.0"\ntokio = { version = "1", features = ["full"] }\n',
        encoding="utf-8",
    )
    (tmp_path / "go.mod").write_text(
        "module example.com/x\n\ngo 1.22\n\nrequire (\n\tgithub.com/gin-gonic/gin v1.9\n)\n",
        encoding="utf-8",
    )
    data = await inspect(tmp_path)
    names = {d["name"] for d in data["dependencies"]}
    assert {"serde", "tokio", "github.com/gin-gonic/gin"} <= names


async def test_no_manifests(tmp_path):
    data = await inspect(tmp_path)
    assert data["dependencies"] == []
