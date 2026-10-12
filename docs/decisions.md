# Architecture Decision Records

The consolidated decision log (§44).

| ADR | Decision | Reason | Consequence |
|---|---|---|---|
| 001 | MIT, src-layout, hatchling | Simple packaging, clean namespace | Dynamic version from `__init__.py` |
| 002 | JSON files = durable truth; SQLite = rebuildable index | Git-friendly, human-inspectable state | Dual writes centralized in `ProjectStores` |
| 003 | Atomic writes + fsync'd events | Interrupts never corrupt state (§36) | Durability priority |
| 004 | Forward-only SQLite migrations | Phase-safe schema upgrades | New tables require new numbered migration |
| 005 | Secrets: env-only, `api_key_env` indirection, `.env` loading | Secrets never in config, git, or prompts (§46) | Setup writes `~/.forgex/.env` `0600` |
| 006 | Argv-only execution; all shells denied | Shell injection structurally impossible (§45) | No pipes or `&&` in command tool |
| 007 | Sanitized child env allowlist | Child processes cannot leak parent env vars | Explicit env passing when needed |
| 008 | Per-agent permission matrix, fail-closed | Least privilege (§32) | Unknown roles get empty permissions |
| 009 | Deterministic verification; quality gates | Models cannot talk past red tests (§56/58) | Supervisor read-only by permission |
| 010 | Ensemble reviewers read-only; explicit bindings | Parallel writers clobber; diversity must be real | Single senior applier resolves findings |
| 011 | Corroboration judge is deterministic code | Auditable, cheap, testable | Jaccard lexical clustering of findings |
| 012 | Tool loop: native tools or JSON protocol fallback | Works with any OpenAI-compatible model (§31) | Fallback enables local/small model support |
| 013 | Structured output: schema in prompt + bounded repair | Robust structured extraction without forced schema API | Max 2 attempts then controlled error |
| 014 | Pre-mutation checkpoints; reversible rollback | All repository modifications reversible (§21) | Safety checkpoint before hard reset |
| 015 | Context: AST index + import graph + lexical scoring | Low token footprint without heavy vector DB | Fast, deterministic file ranking |
| 016 | Pattern redaction at every content on-ramp | Prevents credentials entering model context | Over-redaction preferred to leakage |
| 017 | Transcript budgets (soft warning + hard stop) | Prevents infinite loops blowing context limits | Checkpoint-recoverable stop |
| 018 | Run lock (`run.lock`) with PID liveness check | Prevents concurrent runs corrupting state | Advisory lock per project |
| 019 | Research = official registries only, fixed endpoints | Zero SSRF / prompt injection surface (§8) | No arbitrary web crawling |
| 020 | Degradation is logged, never silent | Observability and operator trust | Warnings emitted when falling back |
