import json
from pathlib import Path

import pytest

from forgex.agents.base import extract_json
from forgex.agents.architect import ArchitectAgent
from forgex.config import load_config
from forgex.models.base import ModelResponse
from forgex.orchestration.events import EventRecorder, read_events
from forgex.schemas.agent import AgentRole
from forgex.schemas.error import AgentOutputError, TaskGraphError
from forgex.schemas.event import EventType
from forgex.schemas.research import ResearchNote
from forgex.sandbox.permissions import permission_set_for
from forgex.tools import ToolExecutor, build_tool_registry, create_context


class FakeRouter:
    def __init__(self, replies: list[str]):
        self.replies = list(replies)
        self.calls = []

    async def generate(self, agent, *, messages, system=None,
                       response_format=None, temperature=None, **kwargs):
        self.calls.append({"messages": messages, "system": system or ""})
        await agent.plan("Build a todo API")
