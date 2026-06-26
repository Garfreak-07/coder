from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from coder_workbench.core.planner_chat_artifacts import (
    PlannerChatTurn,
    PlannerInteractionMode,
    PlannerTaskState,
)


class PlannerChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant", "system"]
    content: str
    created_at: str | None = None


class PlannerChatSessionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_id: str = "default-planner-led"
    planner_agent_id: str = "planner"
    agent_workflow: dict[str, Any] | None = None
    repo: str | None = None
    scopes: list[str] = Field(default_factory=list)
    knowledge_pack_ids: list[str] = Field(default_factory=list)
    skill_pack_ids: list[str] = Field(default_factory=list)
    memory_pack_ids: list[str] = Field(default_factory=list)
    interaction_mode: PlannerInteractionMode = "discuss"


class PlannerChatTurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str
    interaction_mode: PlannerInteractionMode | None = None
    start_if_ready: bool = True


class PlannerChatSessionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    workflow_id: str
    planner_agent_id: str
    agent_workflow: dict[str, Any] = Field(default_factory=dict)
    repo: str | None = None
    scopes: list[str] = Field(default_factory=list)
    knowledge_pack_ids: list[str] = Field(default_factory=list)
    skill_pack_ids: list[str] = Field(default_factory=list)
    memory_pack_ids: list[str] = Field(default_factory=list)
    interaction_mode: PlannerInteractionMode = "discuss"
    messages: list[PlannerChatMessage] = Field(default_factory=list)
    task_state: PlannerTaskState = Field(default_factory=PlannerTaskState)
    generation: int = 0
    last_turn: PlannerChatTurn | None = None
    run_id: str | None = None
    status: Literal["chatting", "ready", "running", "completed", "blocked"] = "chatting"


def message_record(role: Literal["user", "assistant", "system"], content: str) -> PlannerChatMessage:
    return PlannerChatMessage(role=role, content=content, created_at=datetime.now(timezone.utc).isoformat())


__all__ = [
    "PlannerChatMessage",
    "PlannerChatSessionCreateRequest",
    "PlannerChatSessionRecord",
    "PlannerChatTurnRequest",
    "message_record",
]
