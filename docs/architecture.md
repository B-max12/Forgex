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

## State Machine

`INITIALIZING → ANALYZING → RESEARCHING → PLANNING → BUILDING ⇄ REVIEWING → TESTING → SUPERVISING → (COMPLETED | REPAIRING → TESTING …)` with `FAILED` and `CANCELLED` reachable from any active state. Transitions are explicit (`forgex/orchestration/workflow.py`); the engine walks them, saves state at each step, and `--resume` re-enters idempotently.

## Invariants

1. Agents have zero direct I/O — only tools, only within their permission set.
2. Every mutation is checkpointed first; every rollback is reversible.
3. Verification is deterministic; LLM judgment can only worsen a verdict.
4. JSON files in `.forgex/` are the durable truth; SQLite is a rebuildable index.
5. Every significant action emits an event (`forgex logs`).
6. One active run per project (run lock); interrupts never corrupt state.
7. Bounded loops everywhere: repair iterations, tool rounds, transcript chars.

## Data Flow

`events.jsonl` (append-only, fsync) ↔ SQLite mirrors (events, runs, tasks, model_usage, checkpoints, errors) · `state.json`/`tasks.json` (atomic writes) · git commits as checkpoints · `cache/context-index.json` (mtime-invalidated).
