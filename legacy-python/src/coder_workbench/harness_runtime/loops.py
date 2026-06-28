from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


HarnessLoopPhase = Literal[
    "started",
    "prompt_contract",
    "conversation_started",
    "model_turn",
    "tool_call",
    "observation",
    "artifact_candidate",
    "artifact_validation",
    "repair_attempt",
    "completed",
    "blocked",
    "failed",
]


class HarnessLoopLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_model_turns: int = Field(default=8, ge=1)
    max_tool_calls: int = Field(default=32, ge=1)
    max_repair_attempts: int = Field(default=1, ge=0)
    max_command_seconds: int = Field(default=120, ge=1)


class HarnessLoopStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_index: int = Field(ge=0)
    phase: HarnessLoopPhase
    mode: str
    artifact_target: str | None = None
    agent_id: str | None = None
    summary: str
    evidence_refs: list[str] = Field(default_factory=list)
    native_event_refs: list[str] = Field(default_factory=list)
    error: dict[str, str] | None = None


class HarnessLoopTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    request_id: str
    harness_id: str
    mode: str
    provider_id: str
    artifact_target: str | None = None
    limits: HarnessLoopLimits = Field(default_factory=HarnessLoopLimits)
    steps: list[HarnessLoopStep] = Field(default_factory=list)


__all__ = [
    "HarnessLoopLimits",
    "HarnessLoopPhase",
    "HarnessLoopStep",
    "HarnessLoopTrace",
]
