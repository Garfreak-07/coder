from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExecutionRunMemory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inspected_files: list[str] = Field(default_factory=list)
    relevant_paths: list[str] = Field(default_factory=list)
    attempted_patches: list[str] = Field(default_factory=list)
    failed_checks: list[dict[str, Any]] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    blockers: list[dict[str, Any]] = Field(default_factory=list)
