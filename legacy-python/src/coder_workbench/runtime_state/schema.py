from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


BANNED_STATE_PAYLOAD_KEYS = {
    "packet",
    "context_packet",
    "coding_context_packet",
    "full_output",
    "raw_output",
    "graph_run_cache",
    "token_ledger",
    "full_transcript",
}


class ArtifactRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str
    artifact_type: str
    summary: str = ""


class ToolResultRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result_id: str
    action_type: str
    summary: str = ""
    blob_id: str | None = None


class BlobRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    blob_id: str
    media_type: str | None = None
    preview: str = ""


class MemoryRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_id: str
    scope: str
    summary: str = ""


class AgentStateMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message_id: str
    source_agent_id: str
    target: Literal["planner", "executor", "final_report", "all"]
    kind: str
    summary: str
    artifact_refs: list[str] = Field(default_factory=list)
    tool_result_refs: list[str] = Field(default_factory=list)
    blob_refs: list[str] = Field(default_factory=list)


class WorkItemState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    work_item_id: str
    agent_id: str
    status: Literal["pending", "running", "completed", "blocked"]
    summary: str = ""
    execution_result_ref: str | None = None
    blocked_reason: str | None = None


class PlannerState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    planner_order_ref: str | None = None
    planner_decision_ref: str | None = None
    round_summary_ref: str | None = None


class RunControlState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = "running"
    round: int = 0
    blocked_recovery_used: bool = False


class SharedRunState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    workflow_id: str
    user_request: str
    control: RunControlState = Field(default_factory=RunControlState)
    planner: PlannerState = Field(default_factory=PlannerState)
    work_items: dict[str, WorkItemState] = Field(default_factory=dict)
    messages: list[AgentStateMessage] = Field(default_factory=list)
    artifacts: dict[str, ArtifactRef] = Field(default_factory=dict)
    tool_results: dict[str, ToolResultRef] = Field(default_factory=dict)
    blobs: dict[str, BlobRef] = Field(default_factory=dict)
    memory_refs: list[MemoryRef] = Field(default_factory=list)
    final_report_ref: str | None = None
    debug_refs: list[str] = Field(default_factory=list)


class StateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    update_id: str
    run_id: str
    source: str
    channel: Literal[
        "control",
        "planner",
        "work_items",
        "messages",
        "artifacts",
        "tool_results",
        "blobs",
        "memory_refs",
        "final_report",
        "debug_refs",
    ]
    payload: dict[str, Any]

    @field_validator("payload")
    @classmethod
    def reject_large_inline_payloads(cls, value: dict[str, Any]) -> dict[str, Any]:
        bad_path = _first_banned_key(value)
        if bad_path:
            raise ValueError(f"StateUpdate payload contains banned key: {bad_path}")
        return value


def _first_banned_key(value: Any, prefix: str = "") -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            path = f"{prefix}.{key_text}" if prefix else key_text
            if key_text in BANNED_STATE_PAYLOAD_KEYS:
                return path
            found = _first_banned_key(child, path)
            if found:
                return found
    if isinstance(value, list):
        for index, child in enumerate(value):
            found = _first_banned_key(child, f"{prefix}[{index}]")
            if found:
                return found
    return None
