from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


MemoryScope = Literal["workflow", "project"]
MemoryActorRole = Literal["planner", "executor", "runtime"]
WorkflowMemoryCollection = Literal["successful_assignments", "common_blockers", "planner_notes"]
MemoryWriteStatus = Literal["staged", "committed", "rejected"]


class MemoryDelta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: MemoryScope = "workflow"
    workflow_id: str
    collection: WorkflowMemoryCollection
    entry: dict[str, Any]
    evidence_refs: list[str] = Field(default_factory=list)
    actor_id: str
    actor_role: MemoryActorRole
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class StagedMemoryWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    write_id: str = Field(default_factory=lambda: f"memory-write-{uuid4().hex}")
    status: MemoryWriteStatus
    delta: MemoryDelta
    reason: str = ""
    approved_by: str | None = None
    committed_at: str | None = None


class MemoryCommitResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    write_id: str
    status: MemoryWriteStatus
    reason: str = ""
