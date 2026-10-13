import sys

import pytest

from forgex.sandbox.executor import RestrictedLocalExecutor
from forgex.sandbox.policies import CommandPolicy
from forgex.schemas.error import CommandDeniedError, SandboxError


def make_executor(tmp_path, policy=None, approval=None):
    return RestrictedLocalExecutor(
        workspace=tmp_path, policy=policy or CommandPolicy(), approval=approval,
        default_timeout=30, max_output_bytes=100_000,
    )


async def test_runs_command(tmp_path):
    result = await make_executor(tmp_path).run([sys.executable, "-c", "print('hello-tools')"])
    assert result.exit_code == 0
    assert "hello-tools" in result.stdout


async def test_command_not_found(tmp_path):
    result = await make_executor(tmp_path).run(["definitely-not-a-binary-xyz"])
    assert result.exit_code == 127 and "not found" in result.stderr


async def test_timeout_kills(tmp_path):
    result = await make_executor(tmp_path).run(
        [sys.executable, "-c", "import time; time.sleep(10)"], timeout=0.5
    )
    assert result.timed_out


async def test_denied_command_raises(tmp_path):
    with pytest.raises(CommandDeniedError):
        await make_executor(tmp_path).run(["rm", "-rf", "x"])


async def test_cwd_escape_rejected(tmp_path):
    with pytest.raises(SandboxError):
        await make_executor(tmp_path).run([sys.executable, "-V"], cwd="../outside")


async def test_environment_is_sanitized(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGEX_GROQ_API_KEY", "super-secret-value")
    result = await make_executor(tmp_path).run(
        [sys.executable, "-c", "import os; print(os.environ.get('FORGEX_GROQ_API_KEY', 'CLEAN'))"]
    )
    assert "CLEAN" in result.stdout and "super-secret-value" not in result.stdout


async def test_env_extra_is_passed(tmp_path):
    result = await make_executor(tmp_path).run(
        [sys.executable, "-c", "import os; print(os.environ.get('MY_VAR', 'MISSING'))"],
        env={"MY_VAR": "present"},
    )
    assert "present" in result.stdout


async def test_network_command_needs_approval(tmp_path):
    policy = CommandPolicy(network_commands=frozenset({"python"}), approval_mode="ask")
    result = await make_executor(tmp_path, policy=policy,
                                 approval=lambda d: True).run([sys.executable, "-c", "print('ok')"])
    assert result.exit_code == 0
    with pytest.raises(CommandDeniedError):
        await make_executor(tmp_path, policy=policy,
                            approval=lambda d: False).run([sys.executable, "-c", "print('ok')"])


async def test_output_truncation(tmp_path):
    executor = RestrictedLocalExecutor(workspace=tmp_path, policy=CommandPolicy(),
                                       max_output_bytes=100)
    result = await executor.run([sys.executable, "-c", "print('x' * 5000)"])
    assert result.truncated and len(result.stdout) < 5000
