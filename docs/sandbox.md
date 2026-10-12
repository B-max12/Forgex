# Sandbox

When `sandbox.enabled = true` and Docker is installed, every command FORGEX executes (run_command, run_tests, the verification harness — everything) runs inside a hardened container. The Phase 4 restricted local executor is the always-available fallback.

## Enable

```toml
[sandbox]
enabled = true
image = "python:3.12-slim"   # docker pull python:3.12-slim
network = false             # container gets --network none by default
cpu_limit = "2.0"           # docker --cpus
memory_limit = "1g"         # docker --memory
read_only = true            # read-only container rootfs + tmpfs /tmp
```

Check readiness with `forgex doctor` (it verifies image presence).

## Guarantees

| Control | Implementation |
|---|---|
| Host filesystem invisible | only `-v <workspace>:/workspace` is mounted |
| No network by default | `--network none`; set `sandbox.network=true` to allow |
| Least privilege | `--cap-drop ALL`, `--security-opt no-new-privileges` |
| Read-only system | `--read-only` rootfs + tmpfs `/tmp` |
| Resource limits | `--cpus` / `--memory` when configured |
| Your files stay yours | `--user <uid>:<gid>` on POSIX (no root-owned files) |
| No orphans | `--rm` + named containers killed on timeout/interrupt |
