from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TokenBudget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_input_tokens: int = 8000
    max_output_tokens: int = 2000
    max_total_tokens: int | None = None
    managed_by_runtime: bool = True


class AgentRuntimeProfile(BaseModel):
    """Internal profile compiled from AgentRecipe and installed extensions."""

    model_config = ConfigDict(extra="forbid")

    agent_id: str
    role: str
    engine_id: str
    harness_id: str | None = None
    context_profile: str
    token_budget: TokenBudget
    allowed_artifacts: list[str] = Field(default_factory=list)
    plugin_policy: dict[str, Any] = Field(default_factory=dict)
    skill_policy: dict[str, Any] = Field(default_factory=dict)
    memory_policy: dict[str, Any] = Field(default_factory=dict)
    prompt_layers: dict[str, Any] | None = None
    repair_policy: dict[str, Any] = Field(default_factory=dict)
    tool_policy: dict[str, Any] = Field(default_factory=dict)
