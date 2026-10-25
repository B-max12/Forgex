# Changelog

All notable changes to this project will be documented in this file.

## [0.2.0] - 2026-10-26

### Added
- **Delimiter Stack Auto-Closing**: `_repair_json_string` uses a bracket stack to auto-close nested truncated JSON objects and arrays in correct nesting order.
- **Provider Reference Validation**: `ForgexConfig` validates on load that all agent model bindings point to existing providers.
- **Asynchronous Health Queries**: `health_all_async()` in `ModelRouter` for non-blocking provider diagnostics.
- **Dedicated JSON Repair Test Suite**: Full coverage for markdown fencing, unescaped newlines/tabs, escaped quotes, trailing commas, and truncated output.

### Changed
- **Builder Crash Isolation**: Unhandled exceptions in builder tasks record `ErrorRecord` with exception type, mark task `FAILED`, and isolate crashes from halting the entire run.
- **Review & Repair Error Boundaries**: Expert Coder review pass and repair iteration crashes are caught and gracefully degraded with error logging.
- **Supervisor Graceful Degradation**: Supervisor audit crashes trigger `_finish_failure` cleanly instead of leaving dangling locks.
- **Provider Resilience**: OpenAI-compatible provider now cleanly catches JSON decode errors, catches and flags empty choices arrays, and detects context length exceeded errors for fast short-circuiting.
- **Protocol Parity**: Protocol mode now catches `PermissionDeniedError` matching native mode, and includes soft transcript warning at 75% budget.
- **REPL Logging**: History creation and prompt session fallbacks now log informative debug/warning messages instead of swallowing exceptions silently.

## [0.1.0] - 2026-10-06

### Added
- Multi-agent AI software engineering system (Architect, Builder, Expert Coder, Supervisor).
- Permission-gated tool execution layer.
- SQLite durable state and JSONL event store.
- Git checkpointing with reversible rollback.
- Self-healing repair loop with deterministic quality gates.
- Context intelligence (AST indexing, import dependency graph, chunking, retrieval).
- Multi-model ensemble review.
- Docker sandbox execution isolation.
- Typer CLI with full suite of commands.
