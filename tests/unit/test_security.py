from __future__ import annotations

import json

import pytest

from forgex.config import load_config
from forgex.sandbox.permissions import permission_set_for
from forgex.schemas.agent import AgentRole
from forgex.schemas.error import PathViolationError, PermissionDeniedError
from forgex.tools import ToolCall, ToolExecutor, build_tool_registry, create_context
from forgex.utils.paths import resolve_in_workspace
from forgex.utils.redact import redact_patterns


@pytest.mark.parametrize("raw", ["../x", "a/../..", "a/b/../../../c", "./..", "x/../../y"])
def test_traversal_battery_rejected(tmp_path, raw):
    with pytest.raises(PathViolationError):
        resolve_in_workspace(tmp_path, raw)


def test_redact_patterns_scrubs_known_shapes():
    text = ("gsk_abcdefghijklmnopqrstuvwx sk-abcdefghijklmnopqrstuv12 "
            "AKIAIOSFODNN7EXAMPLE ghp_" + "a" * 35 + " "
            'api_key = "supersecretvalue123" '
            "-----BEGIN RSA PRIVATE KEY-----\nabc\n-----END RSA PRIVATE KEY----- "
            "safe_string stays")
    scrubbed = redact_patterns(text)
    for leaked in ("gsk_abc", "sk-abc", "AKIAIOSFODNN7EXAMPLE", "supersecretvalue", "BEGIN RSA"):
        assert leaked not in scrubbed
    assert "safe_string stays" in scrubbed
    assert scrubbed.count("***REDACTED***") >= 4


async def test_permission_denied_for_read_only_agent(tmp_path):
    ctx = create_context(workspace=tmp_path, config=load_config(), agent=AgentRole.ARCHITECT)
    executor = ToolExecutor(registry=build_tool_registry(), permissions=permission_set_for(AgentRole.ARCHITECT), context=ctx)
    call = ToolCall(id="c1", name="write_file", arguments=json.dumps({"path": "x.txt", "content": "1"}))
    with pytest.raises(PermissionDeniedError):
        await executor.execute(call)
