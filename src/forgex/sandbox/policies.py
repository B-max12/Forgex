"""Command policy: allow/deny lists + network rules (spec sections 20, 45, 75).

Decisions are fail-safe: unknown situations ask or deny — never silently
allow.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from forgex.config.schema import ForgexConfig

logger = logging.getLogger("forgex.sandbox")

ApprovalCallback = Callable[[str], bool]

DEFAULT_DENIED: frozenset[str] = frozenset(
    {
        # destructive / system
        "rm",
        "rmdir",
        "sudo",
        "su",
        "doas",
        "shutdown",
        "reboot",
        "poweroff",
        "halt",
        "mkfs",
        "dd",
        "fdisk",
        "format",
        "chmod",
        "chown",
        "kill",
        "killall",
        "pkill",
        "systemctl",
        "service",
        "launchctl",
        "reg",
        "regedit",
        # shells
        "sh",
        "bash",
        "zsh",
        "dash",
        "ksh",
        "csh",
        "tcsh",
        "fish",
        "cmd",
        "powershell",
        "pwsh",
        # argument launchers / bypasses
        "env",
        "xargs",
        "find",
        "nohup",
        "timeout",
        "stdbuf",
        "nice",
        "watch",
        "tee",
    }
)

DEFAULT_NETWORK_COMMANDS: frozenset[str] = frozenset(
    {
        "pip",
        "pip3",
        "uv",
        "npm",
        "npx",
        "pnpm",
        "yarn",
        "bun",
        "cargo",
        "go",
        "curl",
        "wget",
        "docker",
        "podman",
    }
)


class Decision(Enum):
    ALLOW = "allow"
    DENY = "deny"
    APPROVAL = "approval"


@dataclass(frozen=True)
class PolicyDecision:
    decision: Decision
    reason: str = ""


class CommandPolicy:
    def __init__(
        self,
        allowed: frozenset[str] | None = None,
        denied: frozenset[str] | None = None,
        network_commands: frozenset[str] | None = None,
        network_allowed: bool = False,
        approval_mode: str = "ask",
    ) -> None:
        self.allowed = allowed
        self.denied = denied or DEFAULT_DENIED
        self.network_commands = network_commands or DEFAULT_NETWORK_COMMANDS
        self.network_allowed = network_allowed
        self.approval_mode = approval_mode

    @classmethod
    def from_config(cls, config: ForgexConfig) -> CommandPolicy:
        term = config.terminal
        perm = config.permissions
        allowed = frozenset(term.allowed) if term.allowed else None
        denied = frozenset(term.denied) if term.denied else DEFAULT_DENIED
        return cls(
            allowed=allowed,
            denied=denied,
            network_allowed=(perm.mode == "auto"),
            approval_mode=perm.mode,
        )

    def check(self, argv: list[str]) -> PolicyDecision:
        if not argv:
            return PolicyDecision(Decision.DENY, "Empty command line")

        raw_base = argv[0]
        # Resolve command base name
        base = Path(raw_base).name.lower()
        base = base.removesuffix(".exe")

        norm_base = re.sub(r"[0-9.]+$", "", base)

        # 1. Deny list
        if base in self.denied or norm_base in self.denied:
            return PolicyDecision(Decision.DENY, f"Command '{base}' is in the deny list")

        # 2. Allowlist mode
        if self.allowed is not None:
            if base not in self.allowed and norm_base not in self.allowed:
                return PolicyDecision(Decision.DENY, f"Command '{base}' is not in the allowlist")

        # 3. Network commands
        if (base in self.network_commands or norm_base in self.network_commands) and not self.network_allowed:
            return PolicyDecision(Decision.APPROVAL, f"Command '{base}' may access the network")

        return PolicyDecision(Decision.ALLOW)


def resolve_approval(mode: str, description: str, callback: ApprovalCallback | None) -> bool:
    if mode == "safe":
        return False
    if mode == "auto":
        return True
    if mode == "ask":
        if callback is None:
            return False
        try:
            return bool(callback(description))
        except Exception:  # noqa: BLE001
            return False
    return False
