"""Sandbox package: permissions, command policy, and execution (spec sections 19, 20, 45)."""

from forgex.sandbox.executor import (
    CommandExecutor,
    CommandResult,
    DockerExecutor,
    PolicyGatedExecutor,
    RestrictedLocalExecutor,
    build_executor,
    docker_available,
)
from forgex.sandbox.permissions import Permission, PermissionSet, permission_set_for
from forgex.sandbox.policies import (
    ApprovalCallback,
    CommandPolicy,
    Decision,
    PolicyDecision,
    resolve_approval,
)

__all__ = [
    "ApprovalCallback",
    "CommandExecutor",
    "CommandPolicy",
    "CommandResult",
    "Decision",
    "DockerExecutor",
    "Permission",
    "PermissionSet",
    "PolicyDecision",
    "PolicyGatedExecutor",
    "RestrictedLocalExecutor",
    "build_executor",
    "docker_available",
    "permission_set_for",
    "resolve_approval",
]
