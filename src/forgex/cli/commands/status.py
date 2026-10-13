"""`forgex status` — project detection, git state, ProjectState summary and run history."""

from __future__ import annotations

import typer
from rich.panel import Panel

from forgex.cli.ui import JsonFlag, Output, PlainFlag, ui_from
from forgex.config import load_config
from forgex.orchestration.state import StateStore, TaskStore
from forgex.orchestration.stores import open_stores
from forgex.project import detect_project
from forgex.schemas.error import ProjectError
from forgex.schemas.task import TaskStatus
from forgex.tools.git import current_branch, is_dirty
from forgex.utils.paths import find_project_root


def status_command(
    ctx: typer.Context,
    json_out: JsonFlag = False,
    plain: PlainFlag = False,
) -> None:
    """Show project status."""
    ui = ui_from(ctx, json_out=json_out, plain=plain)
    root = find_project_root()
    if root is None:
        raise ProjectError("Not inside a FORGEX project — run `forgex init` first.")

    config = load_config(root)
    detection = detect_project(root)
    branch = current_branch(root)
    dirty = is_dirty(root) if branch else None

    state = StateStore(root).load()
    tasks = TaskStore(root).load()

    task_counts = {s.value: 0 for s in TaskStatus}
    for t in tasks:
        task_counts[t.status.value] += 1

    runs_payload: list[dict] = []
    usage_totals = None
    with open_stores(root, create_db=False) as stores:
        if stores.runs is not None:
            pid = state.project_id if state else None
            runs_payload = [r.model_dump(mode="json") for r in stores.runs.list_recent(pid, limit=5)]
        if stores.usage is not None:
            raw_totals = stores.usage.totals()
            usage_totals = {k: (int(v) if v is not None else None) for k, v in raw_totals.items()}

    events_path = root / ".forgex" / "events.jsonl"
    n_events = (
        sum(1 for ln in events_path.read_text(encoding="utf-8").splitlines() if ln.strip())
        if events_path.is_file()
        else 0
    )
    n_checkpoints = len(list((root / ".forgex" / "checkpoints").glob("*")))
    git_state = f"{branch} ({'dirty' if dirty else 'clean'})" if branch else "not a git repository"

    state_summary = None
    if state:
        state_summary = {
            "project_id": state.project_id,
            "status": state.status.value,
            "iteration": state.iteration,
            "current_agent": state.current_agent.value if state.current_agent else None,
            "current_task": state.current_task,
            "user_request": state.user_request,
            "git_commit": state.git_commit,
            "changed_files": len(state.changed_files),
            "errors": len(state.errors),
            "last_supervisor_status": state.last_supervisor_status,
            "test_results": (
                {
                    "passed": state.test_results.passed,
                    "failed": state.test_results.failed,
                    "exit_code": state.test_results.exit_code,
                }
                if state.test_results
                else None
            ),
        }

    payload = {
        "project": root.name,
        "root": str(root),
        "detection": detection.as_dict(),
        "git": {"branch": branch, "dirty": dirty},
        "state": state_summary,
        "tasks": {"total": len(tasks), "by_status": task_counts},
        "runs": runs_payload,
        "model_usage": usage_totals,
        "checkpoints": n_checkpoints,
        "events": n_events,
        "workflow": {"max_iterations": config.workflow.max_iterations},
        "permissions": {"mode": config.permissions.mode},
    }
    ui.data(payload)

    lines = [
        f"Detected:    {detection.summary()}",
        f"Git:         {git_state}",
        f"Status:      {state.status.value if state else 'no state file'}",
    ]
    if state:
        agent = state.current_agent.value if state.current_agent else "—"
        lines.append(f"Iteration:   {state.iteration}")
        lines.append(f"Current:     agent={agent} task={state.current_task or '—'}")
    lines.append(
        f"Tasks:       {task_counts['completed']}/{len(tasks)} completed"
        + (f", {task_counts['failed']} failed" if task_counts["failed"] else "")
    )
    if state:
        tr = state.test_results
        if tr is not None:
            p = tr.passed if tr.passed is not None else "?"
            f = tr.failed if tr.failed is not None else "?"
            lines.append(f"Tests:       {p} passed, {f} failed (exit {tr.exit_code})")
        else:
            lines.append("Tests:       not run")
        lines.append(f"Supervisor:  {state.last_supervisor_status or 'not run'}")
    lines.extend([
        f"Checkpoints: {n_checkpoints}",
        f"Events:      {n_events}",
        f"Workflow:    max_iterations={config.workflow.max_iterations}",
        f"Permissions: {config.permissions.mode}",
    ])

    if usage_totals and usage_totals.get("calls"):
        tokens_in, tokens_out = usage_totals.get("input_tokens"), usage_totals.get("output_tokens")
        lines.append(
            f"Model usage: {usage_totals['calls']} call(s)"
            + (f", {tokens_in} in / {tokens_out} out tokens" if tokens_in is not None else " (tokens unreported)")
        )

    if ui.mode is Output.RICH:
        ui.console.print(Panel("\n".join(lines), title=f"FORGEX — {root.name}", expand=False))
    elif ui.mode is Output.PLAIN:
        for line in lines:
            ui.console.print(line)
