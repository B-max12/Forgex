"""Per-agent tool permissions (spec section 32).

No agent gets unlimited permissions. Unknown roles get an EMPTY set —
fail closed, always.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from forgex.schemas.agent import AgentRole


class Permission(str, Enum):
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    TERMINAL = "terminal"
    GIT = "git"
    TEST = "test"
    BUILD = "build"
    RESEARCH = "research"
    NETWORK = "network"


class PermissionSet(BaseModel):
    allow: set[Permission] = Field(default_factory=set)

    def permits(self, *permissions: Permission) -> bool:
        return all(p in self.allow for p in permissions)

    def deny_reason(self, *permissions: Permission) -> str | None:
        missing = [p.value for p in permissions if p not in self.allow]
        return f"missing permissions: {', '.join(missing)}" if missing else None


def permission_set_for(role: Any) -> PermissionSet:
    """Return the static permission grant for an agent role."""
    role_val = getattr(role, "value", str(role))

    if role_val == AgentRole.ARCHITECT.value:
        return PermissionSet(allow={Permission.READ, Permission.RESEARCH})
    elif role_val in (AgentRole.BUILDER.value, AgentRole.EXPERT_CODER.value):
        return PermissionSet(
            allow={
                Permission.READ,
                Permission.WRITE,
                Permission.DELETE,
                Permission.TERMINAL,
                Permission.GIT,
                Permission.TEST,
                Permission.BUILD,
            }
        )
    elif role_val == AgentRole.SUPERVISOR.value:
        return PermissionSet(
            allow={
                Permission.READ,
                Permission.TEST,
                Permission.BUILD,
                Permission.GIT,
            }
        )
    return PermissionSet(allow=set())
