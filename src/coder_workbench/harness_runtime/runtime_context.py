from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .contracts import HarnessMode
from .profiles import HarnessRuntimeProfile


class HarnessRuntimeContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    round: int | None = None
    agent_id: str
    workflow_id: str
    harness_id: str
    mode: HarnessMode
    profile_id: str
    repo_root: str | None = None
    sandbox_root: str | None = None
    context_packet: dict[str, Any] | None = None
    capability_set: dict[str, Any] | None = None
    shared_run_state: dict[str, Any] | None = None
    round_working_set: dict[str, Any] | None = None
    budget: dict[str, Any] | None = None
    runtime_settings: dict[str, Any] | None = None
    initial_data: dict[str, Any] = Field(default_factory=dict)


class HarnessRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    contract_id: str
    mode: HarnessMode
    profile: HarnessRuntimeProfile
    context: HarnessRuntimeContext
    input_artifacts: dict[str, Any] = Field(default_factory=dict)


class HarnessRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["completed", "blocked", "failed", "cancelled"]
    artifact_type: str | None = None
    artifact: dict[str, Any] | None = None
    artifact_ref: str | None = None
    native_event_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    diff_refs: list[str] = Field(default_factory=list)
    log_refs: list[str] = Field(default_factory=list)
    token_usage: dict[str, Any] | None = None
    error: dict[str, Any] | None = None


__all__ = [
    "HarnessRunRequest",
    "HarnessRunResult",
    "HarnessRuntimeContext",
]
