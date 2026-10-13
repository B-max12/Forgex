"""Multi-model ensemble review (spec section 15).

N independent reviewer models examine the same diff in parallel, read-only;
findings are synthesized deterministically (corroboration counting = the judge);
the senior Expert Coder applies the justified fixes.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Literal

from forgex.agents.base import BaseAgent, prefetch_files
from forgex.agents.expert_coder import _single_review, build_coder, resolve_review_scope
from forgex.config.schema import AgentModelBinding, ForgexConfig
from forgex.models.router import ModelRouter
from forgex.orchestration.checkpoints import create_checkpoint
from forgex.orchestration.stores import ProjectStores
from forgex.sandbox.permissions import Permission, PermissionSet
from forgex.schemas.agent import AgentRole, ExpertCoderResult, ReviewFinding, ReviewFindings
from forgex.schemas.error import ProjectError, ProviderError
from forgex.schemas.event import EventType
from forgex.schemas.task import Task
from forgex.tools import ToolExecutor, build_tool_registry, create_context

logger = logging.getLogger("forgex.ensemble")

_WORD_RE = re.compile(r"[a-z0-9_]{3,}")


def _tokenize(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


class BindingRouter:
    """Delegates generate() to ModelRouter.generate_with() for a specific binding."""

    def __init__(self, router: ModelRouter, provider: str, model: str) -> None:
        self._router = router
        self.provider = provider
        self.model = model

    def capabilities_for(self, agent: str):
        return self._router.capabilities_for_binding(self.provider, self.model)

    async def generate(self, agent: str, **kwargs) -> Any:
        return await self._router.generate_with(
            provider=self.provider,
            model=self.model,
            agent=agent,
            **kwargs,
        )

    async def aclose(self) -> None:
        pass


class ReviewerAgent(BaseAgent):
    role = AgentRole.EXPERT_CODER
    prompt_name = "reviewer"

    def __init__(
        self,
        *,
        router: Any,
        tools: ToolExecutor,
        label: str,
        events=None,
        run_id=None,
    ) -> None:
        super().__init__(router=router, events=events, run_id=run_id)
        self._tools = tools
        self.label = label

    async def review(
        self,
        *,
        diff: str,
        changed_files: list[str] | None = None,
        task: Task | None = None,
        plan=None,
        research=None,
        errors=None,
    ) -> ReviewFindings:
        existing = prefetch_files(
            self._tools.context.workspace,
            changed_files or [],
            budget=20_000,
            max_files=8,
        )

        parts = [
            f"<diff>\n{diff[:20000]}\n</diff>",
            f"<changed_files>\n{', '.join(changed_files or [])}\n</changed_files>",
        ]
        if task:
            parts.append(f"<task>\n{task.id}: {task.description}\n</task>")
        if plan:
            parts.append(f"<plan>\nGoal: {plan.goal}\n</plan>")
        if existing:
            parts.append(f"<existing_files>\n{existing}\n</existing_files>")

        parts.append(
            "Review the diff above as an independent critic. Report findings with severity and file. Do not edit files."
        )

        loop_res = await self._tool_loop("\n\n".join(parts), self._tools, ReviewFindings)
        return loop_res.report


def synthesize(
    reviews: list[ReviewFindings],
) -> tuple[Literal["ok", "needs_changes"], list[ReviewFinding]]:
    """Synthesize findings across reviewers with corroboration clustering."""
    all_findings: list[tuple[ReviewFinding, int]] = []
    for r_idx, rev in enumerate(reviews):
        for f in rev.findings:
            all_findings.append((f, r_idx))

    clusters: list[list[tuple[ReviewFinding, int]]] = []
    for f, r_idx in all_findings:
        f_toks = _tokenize(f.issue + " " + (f.suggestion or ""))
        matched = False
        for c in clusters:
            c_toks = _tokenize(c[0][0].issue + " " + (c[0][0].suggestion or ""))
            if _jaccard(f_toks, c_toks) >= 0.4:
                c.append((f, r_idx))
                matched = True
                break
        if not matched:
            clusters.append([(f, r_idx)])

    confirmed: list[ReviewFinding] = []
    for c in clusters:
        unique_reviewers = {r_idx for _, r_idx in c}
        lead = c[0][0]
        if len(unique_reviewers) >= 2 or lead.severity == "critical" or len(reviews) == 1:
            confirmed.append(lead)

    needs_changes_count = sum(1 for r in reviews if r.verdict == "needs_changes")
    majority_needs_changes = needs_changes_count > (len(reviews) // 2)

    has_significant_finding = any(f.severity in ("critical", "major") for f in confirmed)

    verdict: Literal["ok", "needs_changes"] = (
        "needs_changes" if (has_significant_finding or majority_needs_changes) else "ok"
    )
    return verdict, confirmed


def resolve_reviewer_bindings(config: ForgexConfig) -> list[AgentModelBinding]:
    if config.ensemble.bindings:
        return config.ensemble.bindings[: config.ensemble.reviewers]

    bindings: list[AgentModelBinding] = []
    ec = config.models.expert_coder
    bindings.append(AgentModelBinding(provider=ec.provider, model=ec.model))

    if config.fallback.enabled:
        for fb_p in config.fallback.providers:
            if fb_p == ec.provider:
                continue
            prov_cfg = config.providers.get(fb_p)
            if prov_cfg and prov_cfg.default_model:
                bindings.append(AgentModelBinding(provider=fb_p, model=prov_cfg.default_model))
                if len(bindings) >= config.ensemble.reviewers:
                    break

    return bindings


def format_synthesis(verdict: str, findings: list[ReviewFinding]) -> str:
    lines = [f"Ensemble review synthesis: verdict={verdict}"]
    if findings:
        lines.append("Corroborated findings to address:")
        for f in findings:
            file_part = f" ({f.file})" if f.file else ""
            sugg_part = f" -> Suggestion: {f.suggestion}" if f.suggestion else ""
            lines.append(f"- [{f.severity.upper()}]{file_part} {f.issue}{sugg_part}")
    else:
        lines.append("No corroborated issues found.")
    return "\n".join(lines)


async def ensemble_review(
    *,
    stores: ProjectStores,
    config: ForgexConfig,
    task_id: str | None = None,
    base_commit: str | None = None,
    applier: Any | None = None,
    approval: Any = None,
) -> ExpertCoderResult | None:
    bindings = resolve_reviewer_bindings(config)
    if len(bindings) < 2:
        logger.warning("Fewer than 2 ensemble bindings available; falling back to single review")
        return await _single_review(
            stores=stores,
            config=config,
            task_id=task_id,
            base_commit=base_commit,
            coder=applier,
            approval=approval,
        )

    scope = resolve_review_scope(stores=stores, task_id=task_id, base_commit=base_commit)
    if scope is None:
        return None
    task, diff, changed = scope

    state = stores.state.load()
    if state is None:
        raise ProjectError("Project state missing")

    create_checkpoint(
        f"pre-ensemble{'-' + task_id if task_id else ''}",
        stores=stores,
        description="Before ensemble review",
        run_id=state.current_run_id,
    )

    router = ModelRouter(config, usage=stores.usage)

    async def _run_one(binding: AgentModelBinding, idx: int) -> ReviewFindings:
        label = f"reviewer_{idx}_{binding.provider}"
        b_router = BindingRouter(router, binding.provider, binding.model or "")
        tool_ctx = create_context(
            workspace=stores.root,
            config=config,
            events=stores.recorder,
            run_id=state.current_run_id,
            agent=AgentRole.EXPERT_CODER,
        )
        tools = ToolExecutor(
            registry=build_tool_registry(),
            permissions=PermissionSet(allow={Permission.READ, Permission.GIT, Permission.TEST}),
            context=tool_ctx,
        )
        agent = ReviewerAgent(
            router=b_router,
            tools=tools,
            label=label,
            events=stores.recorder,
            run_id=state.current_run_id,
        )
        return await agent.review(
            diff=diff,
            changed_files=changed,
            task=task,
            plan=state.architecture_plan,
            research=state.research,
            errors=state.errors,
        )

    tasks = [_run_one(b, i) for i, b in enumerate(bindings)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    valid_reviews: list[ReviewFindings] = []
    failures = 0
    for r in results:
        if isinstance(r, BaseException):
            failures += 1
            logger.warning("Ensemble reviewer failed: %s", r)
        else:
            valid_reviews.append(r)

    if not valid_reviews:
        await router.aclose()
        raise ProviderError("All ensemble reviewers failed")

    verdict, confirmed_findings = synthesize(valid_reviews)

    stores.recorder.record(
        EventType.ENSEMBLE_COMPLETED,
        {
            "reviewers": len(bindings),
            "failures": failures,
            "verdict": verdict,
            "confirmed_findings": len(confirmed_findings),
        },
        run_id=state.current_run_id,
    )

    if verdict == "ok":
        await router.aclose()
        return ExpertCoderResult(
            status="completed",
            summary=f"[ensemble {len(valid_reviews)}/{len(bindings)}] approved without changes",
            changed_files=[],
            improvements=[],
            issues_found=[f.issue for f in confirmed_findings],
            unfixed_issues=[],
        )

    # Apply justified fixes
    synth_text = format_synthesis(verdict, confirmed_findings)
    senior = applier or build_coder(
        config=config,
        workspace=stores.root,
        stores=stores,
        router=router,
        approval=approval,
        run_id=state.current_run_id,
    )
    owns_senior = applier is None
    try:
        applied = await senior.review(
            task=task,
            plan=state.architecture_plan,
            research=state.research,
            diff=diff,
            changed_files=changed,
            errors=state.errors,
            extra_context=synth_text,
        )
    finally:
        if owns_senior:
            await senior.aclose()
        await router.aclose()

    if applied.changed_files:
        state.changed_files = sorted(set(state.changed_files) | set(applied.changed_files))
        stores.save_state(state)

    return applied
