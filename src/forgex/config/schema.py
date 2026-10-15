"""Pydantic models describing FORGEX configuration.

Priority (highest wins), per spec section 27:
    CLI arguments > environment (secrets) > project .forgex/config.toml
    > global ~/.forgex/config.toml > schema defaults.

Secrets NEVER live in these files — providers store only the *name* of
the environment variable holding the key (``api_key_env``).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from forgex.models.capabilities import ModelCapabilities


class WorkflowConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_iterations: int = Field(default=5, ge=1, le=20)


class PermissionsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["auto", "ask", "safe"] = "ask"


class ProviderConfig(BaseModel):
    """A provider endpoint description. Contains no secrets."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["openai_compatible", "groq", "local"] = "openai_compatible"
    base_url: str | None = None
    api_key_env: str | None = None
    default_model: str | None = None
    timeout_seconds: float = 60.0
    max_retries: int = 2


class AgentModelBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = "groq"
    model: str | None = None


class ModelsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    architect: AgentModelBinding = Field(default_factory=AgentModelBinding)
    builder: AgentModelBinding = Field(default_factory=AgentModelBinding)
    expert_coder: AgentModelBinding = Field(default_factory=AgentModelBinding)
    supervisor: AgentModelBinding = Field(default_factory=AgentModelBinding)
    capabilities: dict[str, ModelCapabilities] = Field(default_factory=dict)


class FallbackConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    providers: list[str] = Field(default_factory=list)
    on_rate_limit: bool = Field(
        default=True,
        description="Automatically switch to fallback providers when the primary is rate-limited (429). "
        "Works even when 'enabled' is False — set to False to disable all automatic switching.",
    )
    cooldown_seconds: int = Field(
        default=60,
        ge=10,
        le=600,
        description="Seconds to avoid a rate-limited provider before trying it again.",
    )


class TerminalConfig(BaseModel):
    """Command execution policy knobs (spec sections 19, 45)."""

    model_config = ConfigDict(extra="forbid")

    allowed: list[str] = Field(default_factory=list)
    denied: list[str] = Field(default_factory=list)
    timeout_seconds: int = 120
    max_output_bytes: int = 1_000_000


class SandboxConfig(BaseModel):
    """Docker sandbox (spec section 20). Default: restricted."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    network: bool = False
    image: str = "python:3.12-slim"
    cpu_limit: str | None = None
    memory_limit: str | None = None
    read_only: bool = True
    user: str | None = None
    timeout_seconds: int = 120


class ResearchConfig(BaseModel):
    """Web research toggle (spec sections 8, 73)."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True


class EnsembleConfig(BaseModel):
    """Multi-model ensemble review (spec section 15)."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    reviewers: int = Field(default=2, ge=2, le=4)
    bindings: list[AgentModelBinding] = Field(default_factory=list)


def _default_providers() -> dict[str, ProviderConfig]:
    return {
        "groq": ProviderConfig(
            type="groq",
            base_url="https://api.groq.com/openai/v1",
            api_key_env="FORGEX_GROQ_API_KEY",
            default_model="llama-3.3-70b-versatile",
        ),
        "openai_compatible": ProviderConfig(
            type="openai_compatible",
            base_url="https://api.openai.com/v1",
            api_key_env="FORGEX_OPENAI_API_KEY",
            default_model="gpt-4o-mini",
        ),
        "local": ProviderConfig(
            type="local",
            base_url="http://localhost:11434/v1",
        ),
    }


class ForgexConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow: WorkflowConfig = Field(default_factory=WorkflowConfig)
    permissions: PermissionsConfig = Field(default_factory=PermissionsConfig)
    terminal: TerminalConfig = Field(default_factory=TerminalConfig)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    research: ResearchConfig = Field(default_factory=ResearchConfig)
    ensemble: EnsembleConfig = Field(default_factory=EnsembleConfig)
    fallback: FallbackConfig = Field(default_factory=FallbackConfig)
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    providers: dict[str, ProviderConfig] = Field(default_factory=_default_providers)
