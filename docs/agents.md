# Agents

All agents share one machinery: versioned prompts (`prompts/*.md`, `name:vN`), the structured-output loop (schema-in-prompt → parse → bounded repair), and — for acting agents — the **tool loop**: multi-turn native tool calling, or a strict JSON protocol for models without tool support. The loop itself has zero privileges; every call goes through the per-agent permission set at the `ToolExecutor`.

| Agent | Prompt | Permissions | Output |
|---|---|---|---|
| Architect | `architect:v1` | read, research | `AnalysisResult` → `ArchitecturePlan` |
| Builder | `builder:v1` | read, write, delete, terminal, git, test, build | `BuilderResult` |
| Expert Coder | `expert_coder:v1` | read, write, delete, terminal, git, test, build | `ExpertCoderResult` |
| Reviewer | `reviewer:v1` | read, git, test | `ReviewFindings` |
| Supervisor | `supervisor:v1` | read, test, build, git | `SupervisorJudgment` → `SupervisorReport` |

## Collaboration Protocol

1. **Architect** analyzes repository and decomposes goals into dependency-ordered tasks (`TASK-001`, `TASK-002`, ...).
2. **Builder** implements tasks one at a time within pre-task checkpoints.
3. **Expert Coder** inspects diffs and refines changes (or ensemble reviewers corroborated by judge).
4. **Supervisor** audits deterministic test/build results against acceptance criteria and issues verdicts.
5. In case of failure, a `REPAIR-NNN` task is generated for targeted self-healing.
