"""Restricted command execution (spec sections 19, 20, 45, 75).

Every command runs as an ARGV LIST — never a shell string.
Guarantees:
  * cwd must resolve inside the workspace (path traversal rejected)
  * child environment is sanitized (parent secrets are never inherited)
  * timeouts are enforced
  * Docker sandbox option with container confinement
"""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
import shutil
import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from forgex.config.schema import ForgexConfig
from forgex.sandbox.policies import (
    ApprovalCallback,
    CommandPolicy,
    Decision,
    resolve_approval,
)
from forgex.schemas.error import CommandDeniedError, SandboxError
from forgex.utils.paths import resolve_in_workspace

logger = logging.getLogger("forgex.sandbox")

_SAFE_ENV_VARS = (
    "PATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TERM",
    "USERPROFILE",
    "SYSTEMROOT",
    "SYSTEMDRIVE",
    "COMSPEC",
    "PATHEXT",
    "TEMP",
    "TMP",
)


@dataclass
class CommandResult:
    argv: list[str]
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    duration_ms: float = 0.0
    truncated: bool = False


class CommandExecutor(ABC):
    @abstractmethod
    async def run(
        self,
        command: list[str] | str,
        *,
        cwd: str = ".",
        timeout: float | None = None,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        pass


class PolicyGatedExecutor(CommandExecutor):
    def __init__(
        self,
        workspace: Path,
        policy: CommandPolicy,
        approval: ApprovalCallback | None = None,
        default_timeout: int = 120,
        max_output_bytes: int = 1_000_000,
    ) -> None:
        self.workspace = Path(workspace).resolve()
        self.policy = policy
        self.approval = approval
        self.default_timeout = default_timeout
        self.max_output_bytes = max_output_bytes

    async def run(
        self,
        command: list[str] | str,
        *,
        cwd: str = ".",
        timeout: float | None = None,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        if isinstance(command, str):
            argv = shlex.split(command)
        else:
            argv = list(command)

        if not argv:
            raise CommandDeniedError("Empty command")

        # 1. Policy check
        decision = self.policy.check(argv)
        if decision.decision is Decision.DENY:
            raise CommandDeniedError(f"Command denied by policy: {decision.reason}")
        if decision.decision is Decision.APPROVAL:
            approved = resolve_approval(self.policy.approval_mode, shlex.join(argv), self.approval)
            if not approved:
                raise CommandDeniedError(f"Command not approved: {shlex.join(argv)}")

        # 2. Working directory confinement
        try:
            workdir = resolve_in_workspace(self.workspace, cwd)
        except Exception as exc:
            raise SandboxError(f"Working directory escapes workspace: {exc}") from exc

        return await self._execute(argv, workdir, timeout or self.default_timeout, env)

    @abstractmethod
    async def _execute(
        self,
        argv: list[str],
        workdir: Path,
        timeout: float,
        env: Mapping[str, str] | None,
    ) -> CommandResult:
        pass


class RestrictedLocalExecutor(PolicyGatedExecutor):
    async def _execute(
        self,
        argv: list[str],
        workdir: Path,
        timeout: float,
        env: Mapping[str, str] | None,
    ) -> CommandResult:
        # Sanitize environment
        child_env: dict[str, str] = {}
        for var in _SAFE_ENV_VARS:
            val = os.environ.get(var)
            if val is not None:
                child_env[var] = val
        if env:
            child_env.update(env)

        start = time.perf_counter()
        timed_out = False
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                cwd=str(workdir),
                env=child_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            duration = (time.perf_counter() - start) * 1000
            return CommandResult(
                argv=argv,
                exit_code=127,
                stderr=f"command not found: {argv[0]}",
                duration_ms=duration,
            )
        except OSError as exc:
            duration = (time.perf_counter() - start) * 1000
            return CommandResult(
                argv=argv,
                exit_code=126,
                stderr=f"failed to execute command: {exc}",
                duration_ms=duration,
            )

        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            timed_out = True
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            stdout_b, stderr_b = await proc.communicate()
        except asyncio.CancelledError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            raise

        duration = (time.perf_counter() - start) * 1000
        truncated = False
        if len(stdout_b) > self.max_output_bytes:
            stdout_b = stdout_b[: self.max_output_bytes]
            truncated = True
        if len(stderr_b) > self.max_output_bytes:
            stderr_b = stderr_b[: self.max_output_bytes]
            truncated = True

        return CommandResult(
            argv=argv,
            exit_code=proc.returncode if proc.returncode is not None else -1,
            stdout=stdout_b.decode("utf-8", errors="replace"),
            stderr=stderr_b.decode("utf-8", errors="replace"),
            timed_out=timed_out,
            duration_ms=duration,
            truncated=truncated,
        )


class DockerExecutor(PolicyGatedExecutor):
    DEFAULT_IMAGE = "python:3.12-slim"

    def __init__(
        self,
        workspace: Path,
        policy: CommandPolicy,
        approval: ApprovalCallback | None = None,
        image: str = DEFAULT_IMAGE,
        cpu_limit: str | None = None,
        memory_limit: str | None = None,
        network: bool = False,
        read_only: bool = True,
        user: str | None = None,
        default_timeout: int = 120,
        max_output_bytes: int = 1_000_000,
    ) -> None:
        super().__init__(workspace, policy, approval, default_timeout, max_output_bytes)
        self.image = image
        self.cpu_limit = cpu_limit
        self.memory_limit = memory_limit
        self.network = network
        self.read_only = read_only
        self.user = user

    def build_docker_argv(
        self,
        argv: list[str],
        workdir: Path,
        container_name: str,
        env: Mapping[str, str] | None = None,
    ) -> list[str]:
        cmd = [
            "docker",
            "run",
            "--rm",
            "--name",
            container_name,
            "--network",
            "bridge" if self.network else "none",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
        ]
        if self.read_only:
            cmd.extend(["--read-only", "--tmpfs", "/tmp"])
        if self.cpu_limit:
            cmd.extend(["--cpus", self.cpu_limit])
        if self.memory_limit:
            cmd.extend(["--memory", self.memory_limit])

        # UID/GID
        if self.user:
            cmd.extend(["--user", self.user])
        elif os.name == "posix":
            cmd.extend(["--user", f"{os.getuid()}:{os.getgid()}"])

        # Mount workspace
        ws_resolved = self.workspace.resolve()
        cmd.extend(["-v", f"{ws_resolved}:/workspace"])

        # Working directory inside container
        try:
            rel = workdir.relative_to(ws_resolved).as_posix()
            w_path = f"/workspace/{rel}" if rel and rel != "." else "/workspace"
        except ValueError:
            w_path = "/workspace"
        cmd.extend(["-w", w_path])

        if env:
            for k, v in env.items():
                cmd.extend(["-e", f"{k}={v}"])

        cmd.append(self.image)
        cmd.extend(argv)
        return cmd

    async def _execute(
        self,
        argv: list[str],
        workdir: Path,
        timeout: float,
        env: Mapping[str, str] | None,
    ) -> CommandResult:
        name = f"forgex-{uuid.uuid4().hex[:8]}"
        docker_cmd = self.build_docker_argv(argv, workdir, name, env)

        start = time.perf_counter()
        timed_out = False
        try:
            proc = await asyncio.create_subprocess_exec(
                *docker_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as exc:
            duration = (time.perf_counter() - start) * 1000
            return CommandResult(
                argv=argv,
                exit_code=125,
                stderr=f"docker execution failed: {exc}",
                duration_ms=duration,
            )

        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            timed_out = True
            try:
                # Force kill container
                kill_p = await asyncio.create_subprocess_exec(
                    "docker", "kill", name,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await kill_p.wait()
                proc.kill()
            except Exception:  # noqa: BLE001
                pass
            stdout_b, stderr_b = await proc.communicate()
        except asyncio.CancelledError:
            try:
                kill_p = await asyncio.create_subprocess_exec(
                    "docker", "kill", name,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await kill_p.wait()
                proc.kill()
            except Exception:  # noqa: BLE001
                pass
            raise

        duration = (time.perf_counter() - start) * 1000
        truncated = False
        if len(stdout_b) > self.max_output_bytes:
            stdout_b = stdout_b[: self.max_output_bytes]
            truncated = True
        if len(stderr_b) > self.max_output_bytes:
            stderr_b = stderr_b[: self.max_output_bytes]
            truncated = True

        return CommandResult(
            argv=argv,
            exit_code=proc.returncode if proc.returncode is not None else -1,
            stdout=stdout_b.decode("utf-8", errors="replace"),
            stderr=stderr_b.decode("utf-8", errors="replace"),
            timed_out=timed_out,
            duration_ms=duration,
            truncated=truncated,
        )


def docker_available() -> bool:
    return shutil.which("docker") is not None


def build_executor(
    workspace: Path,
    config: ForgexConfig,
    approval: ApprovalCallback | None = None,
) -> CommandExecutor:
    policy = CommandPolicy.from_config(config)
    if config.sandbox.enabled:
        if docker_available():
            sb = config.sandbox
            return DockerExecutor(
                workspace=workspace,
                policy=policy,
                approval=approval,
                image=sb.image,
                cpu_limit=sb.cpu_limit,
                memory_limit=sb.memory_limit,
                network=sb.network,
                read_only=sb.read_only,
                user=sb.user,
                default_timeout=sb.timeout_seconds,
                max_output_bytes=config.terminal.max_output_bytes,
            )
        logger.warning("sandbox.enabled is true but docker is not available — using restricted local executor")

    return RestrictedLocalExecutor(
        workspace=workspace,
        policy=policy,
        approval=approval,
        default_timeout=config.terminal.timeout_seconds,
        max_output_bytes=config.terminal.max_output_bytes,
    )


def make_executor(
    workspace: Path | str,
    *,
    policy: CommandPolicy | None = None,
    approval: ApprovalCallback | None = None,
) -> PolicyGatedExecutor:
    return RestrictedLocalExecutor(
        workspace=workspace,
        policy=policy or CommandPolicy(),
        approval=approval,
    )
