# FORGEX

**Plan. Build. Refine. Verify.**

FORGEX is a CLI-first autonomous AI software engineering system. Specialized
agents — **Architect**, **Builder**, **Expert Coder**, **Supervisor** —
collaborate on a real repository through permission-gated tools, Git
checkpoints, a deterministic verification harness, and a bounded self-healing
repair loop.

> FORGEX is not a chatbot and not a code generator: it is an AI software
> engineering *runtime* — with the safety rails that implies.

```
request → Architect → research → plan → [ Builder → Expert Coder →
tests → Supervisor → PASS? done : repair ↺ ] (bounded by max_iterations)
```

**Status: v0.1.0 alpha** — the full pipeline works end-to-end with any
OpenAI-compatible provider (Groq, OpenAI, local servers). Multi-model
ensemble review, Docker sandboxing, and a context-intelligence layer are
built in.

## Installation

```bash
pip install forgex          # once published
pipx install forgex         # recommended (isolated)
uv tool install forgex
```

From source:

```bash
git clone https://github.com/forgex-dev/forgex && cd forgex
pip install -e ".[dev]"
```

Python 3.12+. Optional: Git (checkpoints — strongly recommended),
Docker (sandboxing), ripgrep (faster search).

## Quickstart

```bash
forgex doctor                       # verify your environment
forgex config setup                 # interactive: provider, models, keys
mkdir my-project && cd my-project
forgex init                         # scaffolds .forgex/, detects your project

forgex plan "Create a FastAPI Todo API with SQLite, CRUD and pytest tests."
forgex task list                    # the planned, dependency-ordered tasks
forgex task run TASK-001            # builder + expert review per task
forgex build                        # …or run the whole pipeline with the
                                    # self-healing loop and final report
forgex status && forgex logs
```

Tip: `forgex --offline` disables web research and remote providers (local models only, §73).

## Commands

| Command | Purpose |
|---|---|
| `forgex init [DIR]` | initialize a project (state, events, SQLite index) |
| `forgex plan [REQUEST] [--dry-run]` | Architect: analysis → registry research → implementation plan |
| `forgex build [REQUEST] [--file F] [--resume] [--dry-run]` | full pipeline with the repair loop |
| `forgex fix` | verify + supervise + repair until green — no rebuild |
| `forgex run [-- CMD]` | run the project's start command (policy-gated) |
| `forgex task list / run ID` | inspect / execute single tasks (Builder + review) |
| `forgex review [TASK] [--base C]` | Expert Coder review — single model or ensemble |
| `forgex verify` | deterministic tests/build/lint — no LLM |
| `forgex supervise` | verification + LLM audit + quality gates → verdict |
| `forgex status / logs / diff` | project state, event stream, git diff |
| `forgex checkpoint / rollback` | Git checkpoints; reversible rollback |
| `forgex models [catalog\|health]` | bindings, capability catalog, live provider ping |
| `forgex context stats\|search` | context index and relevance retrieval |
| `forgex tools list\|run` | inspect / manually run agent tools |
| `forgex config show\|get\|set\|setup` | layered configuration |
| `forgex doctor [--ping]` | environment and provider health |

Every command supports `--json` and `--plain` (CI/SSH friendly).

## Providers

| Type | Target | Notes |
|---|---|---|
| `groq` | Groq API | default binding: llama-3.3-70b-versatile |
| `openai_compatible` | OpenAI & any compatible endpoint | set base_url |
| `local` | Ollama, llama.cpp, vLLM, LM Studio | base_url required, keyless |

Provider-independent by design: per-agent model bindings, capability-aware
routing, retry with backoff, fallback chains, and multi-model ensemble
review (`[ensemble] enabled = true` — e.g. Groq + OpenAI reviewing the same
diff in parallel, findings corroborated before fixes are applied).

## Security

- Agents act only through permission-gated tools; every path is workspace-confined; `.forgex/`, `.git/` and secret files are untouchable.
- Commands are argv-only (no shells), policy-filtered (deny list, optional allowlist, network approval), and — with `[sandbox] enabled = true` — run in hardened Docker containers (no network by default, host FS invisible).
- Secrets never enter prompts: env-only storage, sanitized child environments, pattern-based content scrubbing.
- Deterministic quality gates: no model verdict can pass a red test suite or an incomplete build.

Full model + residual risks: `docs/security.md`.

## License

MIT
