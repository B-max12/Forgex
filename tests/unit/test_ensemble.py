from __future__ import annotations

from forgex.agents.ensemble import (
    format_synthesis,
    resolve_reviewer_bindings,
    synthesize,
)
from forgex.config.schema import (
    AgentModelBinding,
    EnsembleConfig,
    FallbackConfig,
    ForgexConfig,
    ModelsConfig,
    ProviderConfig,
)
from forgex.schemas.agent import ReviewFinding, ReviewFindings


def make_config(**ensemble) -> ForgexConfig:
    return ForgexConfig(
        models=ModelsConfig(
            expert_coder=AgentModelBinding(provider="groq", model="llama-3.3-70b-versatile"),
        ),
        providers={
            "groq": ProviderConfig(type="groq", base_url="https://api.groq.com/openai/v1",
                                   default_model="llama-3.3-70b-versatile"),
            "openai_compatible": ProviderConfig(
                type="openai_compatible", base_url="https://api.openai.com/v1",
                default_model="gpt-4o-mini"),
        },
        fallback=FallbackConfig(enabled=True, providers=["openai_compatible"]),
        ensemble=EnsembleConfig(enabled=True, **ensemble),
    )


def test_resolve_reviewer_bindings():
    cfg = make_config(reviewers=2)
    bindings = resolve_reviewer_bindings(cfg)
    assert len(bindings) == 2
    assert bindings[0].provider == "groq"
    assert bindings[1].provider == "openai_compatible"


def test_synthesize_agreement():
    r1 = ReviewFindings(verdict="needs_changes", findings=[ReviewFinding(issue="bug in parser", severity="critical")])
    r2 = ReviewFindings(verdict="needs_changes", findings=[ReviewFinding(issue="bug in parser logic", severity="critical")])
    verdict, confirmed = synthesize([r1, r2])
    assert verdict == "needs_changes"
    assert len(confirmed) >= 1


def test_synthesize_all_ok():
    r1 = ReviewFindings(verdict="ok", findings=[])
    r2 = ReviewFindings(verdict="ok", findings=[])
    verdict, confirmed = synthesize([r1, r2])
    assert verdict == "ok"
    assert confirmed == []


def test_format_synthesis():
    text = format_synthesis("ok", [])
    assert "No corroborated issues found" in text
