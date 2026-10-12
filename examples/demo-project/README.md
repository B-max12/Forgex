FORGEX demo project
A deliberately simple, machine-verifiable task: two unimplemented functionsand a failing test suite. This is the primary E2E demonstration (spec §38).

Run it
cd examples/demo-projectforgex initgit initexport FORGEX_GROQ_API_KEY="gsk_..."   # or your providerforgex build "Implement add() and multiply() in src/demo/calc.py so that all tests pass."# Watch: plan → builder → expert review → tests (red) → supervisor → repair# → tests (green) → supervisor → COMPLETE.forgex status        # tests: 2 passed, supervisor: passforgex logspython -m pytest -q  # verify with your own eyes — never trust, verify
The acceptance criterion is objective: pytest exits 0 with 2 passing tests,
and forgex build reports COMPLETE with the supervisor's approval.

text


---

## Documentation

**`README.md`** ✏ (release rewrite)

````markdown
# FORGEX

**Plan. Build. Refine. Verify.**

FORGEX is a CLI-first autonomous AI software engineering system. Specialized
agents — **Architect**, **Builder**, **Expert Coder**, **Supervisor** —
collaborate on a real repository through permission-gated tools, Git
checkpoints, a deterministic verification harness, and a bounded self-healing
repair loop.

> FORGEX is not a chatbot and not a code generator: it is an AI software
> engineering *runtime* — with the safety rails that implies.

request → Architect → research → plan → [ Builder → Expert Coder →
tests → Supervisor → PASS? done : repair ↺ ] (bounded by max_iterations)

text


**Status: v0.1.0 alpha** — the full pipeline works end-to-end with any
OpenAI-compatible provider (Groq, OpenAI, local servers). Multi-model
ensemble review, Docker sandboxing, and a context-intelligence layer are
built in. See *Limitations* below for the honest list.

## Installation

```bash
pip install forgex          # once published
pipx install forgex         # recommended (isolated)
uv tool install forgex
From source:

bash

git clone https://github.com/forgex-dev/forgex && cd forgex
pip install -e ".[dev]"
Python 3.12+. Optional: Git (checkpoints — strongly recommended),
Docker (sandboxing), ripgrep (faster search).

Quickstart
bash

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
Try the prepared demo: examples/demo-project/ (a failing test FORGEX must
make pass).

Commands
Command
Purpose
forgex init [DIR]	initialize a project (state, events, SQLite index)
forgex plan [REQUEST] [--dry-run]	Architect: analysis → registry research → implementation plan
forgex build [REQUEST] [--file F] [--resume] [--dry-run]	full pipeline with the repair loop
forgex task list / run ID	inspect / execute single tasks (Builder + review)
forgex review [TASK] [--base C]	Expert Coder review — single model or ensemble
forgex verify	deterministic tests/build/lint — no LLM
forgex supervise	verification + LLM audit + quality gates → verdict
forgex status / logs / diff	project state, event stream, git diff
forgex checkpoint / rollback	Git checkpoints; reversible rollback
forgex models [catalog|health]	bindings, capability catalog, live provider ping
forgex context stats|search	context index and relevance retrieval
forgex tools list|run	inspect / manually run agent tools
forgex config show|get|set|setup	layered configuration
forgex doctor [--ping]	environment and provider health

Every command supports --json and --plain (CI/SSH friendly).

Providers
Type
Target
Notes
groq	Groq API	default binding: llama-3.3-70b-versatile
openai_compatible	OpenAI & any compatible endpoint	set base_url
local	Ollama, llama.cpp, vLLM, LM Studio	base_url required, keyless

Provider-independent by design: per-agent model bindings, capability-aware
routing, retry with backoff, fallback chains, and multi-model ensemble
review ([ensemble] enabled = true — e.g. Groq + OpenAI reviewing the same
diff in parallel, findings corroborated before fixes are applied).

Security
Agents act only through permission-gated tools; every path is
workspace-confined; .forgex/, .git/ and secret files are untouchable.
Commands are argv-only (no shells), policy-filtered (deny list, optional
allowlist, network approval), and — with [sandbox] enabled = true — run in
hardened Docker containers (no network by default, host FS invisible).
Secrets never enter prompts: env-only storage, sanitized child environments,
pattern-based content scrubbing.
Deterministic quality gates: no model verdict can pass a red test suite
or an incomplete build.
Full model + residual risks: docs/security.md.
Documentation
Architecture — layers, state machine, invariants
Agents — roles, prompts, permissions, the tool loop
Configuration — every section and default
Providers · Sandbox · Security
Development
bash

pip install -e ".[dev]"
pytest -q && ruff check . && mypy src
See CONTRIBUTING.md — including the project's honesty
rules: never claim a test passed unless you ran it.

Limitations (v0.1.0)
Local (non-sandboxed) execution gates commands, not behavior — enable the
sandbox for untrusted projects.
Best-effort language support: Python is first-class (tests/build/lint,
AST context); JS/TS partial; other ecosystems verify by exit code only.
Secret redaction and dependency research are pattern/registry-based.
The JSON tool-protocol fallback for non-tool-calling models is functional
but slower than native tool calling.
Roadmap
Patch-mode file edits, more language adapters, semantic context retrieval,
persistent sandbox containers, a server/dashboard mode on the same engine.

License
MIT

text


**`docs/architecture.md`** ✚

```markdown
# Architecture

## Layers

```
CLI (Typer/Rich)      thin commands — services hold the logic (future server reuses them)
Orchestration         workflow engine · state · events · checkpoints · run lock
Agents                architect · builder · expert coder · reviewer · supervisor
Model layer           provider adapters · router (bindings, fallback, ensemble) · registry
Tools (permission-    filesystem · search · terminal · git · tests · dependencies
gated, the ONLY        context: index · dependency graph · retrieval · chunking
I/O path for agents)
Storage               SQLite (queryable metadata) + JSON state in .forgex/ (truth)
                      + git (checkpoints) — filesystem stays the source of truth
```

## State machine

`INITIALIZING → ANALYZING → RESEARCHING → PLANNING → BUILDING ⇄ REVIEWING →
TESTING → SUPERVISING → (COMPLETED | REPAIRING → TESTING …)` with FAILED and
CANCELLED reachable from any active state. Transitions are explicit
(`forgex/orchestration/workflow.py`); the engine walks them, saves state at
each step, and `--resume` re-enters idempotently.

## Invariants

1. Agents have zero direct I/O — only tools, only within their permission set.
2. Every mutation is checkpointed first; every rollback is reversible.
3. Verification is deterministic; LLM judgment can only worsen a verdict.
4. JSON files in `.forgex/` are the durable truth; SQLite is a rebuildable index.
5. Every significant action emits an event (`forgex logs`).
6. One active run per project (run lock); interrupts never corrupt state.
7. Bounded loops everywhere: repair iterations, tool rounds, transcript chars.

## Data flow

`events.jsonl` (append-only, fsync) ↔ SQLite mirrors (events, runs, tasks,
model_usage, checkpoints, errors) · `state.json`/`tasks.json` (atomic writes)
· git commits as checkpoints · `cache/context-index.json` (mtime-invalidated).
```

**`docs/agents.md`** ✚

```markdown
# Agents

All agents share one machinery: versioned prompts (`prompts/*.md`,
`name:vN`), the structured-output loop (schema-in-prompt → parse → bounded
repair), and — for acting agents — the **tool loop**: multi-turn native tool
calling, or a strict JSON protocol for models without tool support. The loop
itself has zero privileges; every call goes through the per-agent permission
set at the `ToolExecutor`.

| Agent | Prompt | Permissions | Output |
|---|---|---|---|
| Architect | architect:v1 | read, research | `AnalysisResult` → `ArchitecturePlan` |
| Builder | builder:v1 | read, write, delete, terminal, git, test | `BuilderResult` |


phase 15 

