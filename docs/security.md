# Security

FORGEX executes AI-generated code and commands on your machine. This document is the honest security model — mitigations AND residual risks (spec sections 19, 20, 45, 46, 47, 75).

## The Defense Stack

1. **Workspace confinement** — every agent path goes through `resolve_in_workspace`: `..` traversal, absolute escapes, and symlink escapes are rejected. `.forgex/` and `.git/` are system-owned; the workspace root is untouchable.
2. **Command policy** (deny list incl. all shells + argument launchers, optional allowlist, network-command approval, auto/ask/safe modes) → approval gate → sandbox (Docker: no host FS outside workspace mount, `--network none` by default, dropped capabilities, read-only rootfs, uid-mapped).
3. **Argv-only execution** — commands are never interpreted by a shell; shell injection is structurally impossible. Git operations (including rollback) are argv-based: forged commit values fail as invalid revisions.
4. **Secret hygiene** — keys live only in env vars; child environment is a sanitized allowlist; `.env`-style files are unreadable by agents; all content entering model context is pattern-scrubbed (`redact_patterns`); provider error text is redacted.
5. **Untrusted data discipline** (§47) — repository content only ever enters prompts inside tagged blocks in user messages; system prompts are static. Instructions inside repo content are treated strictly as data.
6. **Deterministic gates** — no model verdict can pass a red test suite or an incomplete build.
7. **Recoverability** — checkpoints before every mutation; rollback always creates a safety checkpoint first; interrupts save state; one active run per project (`run.lock`).

## Residual Limitations (Known & Accepted)

- Without the Docker sandbox, locally executed processes (e.g. `python -c ...`) can read host files outside the workspace — policy gates commands, not behavior. Enable `sandbox.enabled` for behavioral containment.
- Secret redaction is pattern-based. Non-obvious secret formats (arbitrary high-entropy strings without key-shaped names) can pass through. Never point FORGEX at directories holding real production credentials.
- A TOCTOU window remains between path resolution and file mutation (final-component symlinks are refused).
- Verification commands run with project dependencies — untrusted projects with malicious `conftest.py` should be run inside the Docker sandbox.
