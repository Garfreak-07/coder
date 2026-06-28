from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from coder_workbench.memory.models import (
    AgentMemoryRole,
    MemoryAllowedContext,
    MemoryPurpose,
    MemoryScope,
    MemorySourceRef,
)


RetrievalChannel = Literal["dense", "bm25", "hybrid"]
HybridRagItemType = Literal["knowledge_chunk", "memory_record"]


class HybridRagRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: AgentMemoryRole
    requested_context: MemoryAllowedContext
    query: str

    project_id: str | None = None
    session_id: str | None = None
    run_id: str | None = None

    scope_paths: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    top_k: int = Field(default=8, ge=1, le=20)
    dense_k: int = Field(default=24, ge=1, le=100)
    bm25_k: int = Field(default=24, ge=1, le=100)

    dense_weight: float | None = Field(default=None, ge=0.0, le=1.0)
    bm25_weight: float | None = Field(default=None, ge=0.0, le=1.0)

    include_content: bool = False
    content_preview_chars: int = Field(default=800, ge=0, le=2000)


class RetrievalHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    item_type: HybridRagItemType
    rank: int
    score: float
    channel: RetrievalChannel


class HybridRagResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    item_type: HybridRagItemType
    title: str
    summary: str
    text_preview: str | None = None

    scope: MemoryScope
    purpose: list[MemoryPurpose]
    tags: list[str] = Field(default_factory=list)

    source_refs: list[MemorySourceRef] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    evidence_kind: Literal["knowledge_hint"] = "knowledge_hint"
    requires_repo_verification: bool = False

    dense_rank: int | None = None
    bm25_rank: int | None = None
    dense_score: float | None = None
    bm25_score: float | None = None
    fusion_score: float

    token_estimate: int
    metadata: dict[str, Any] = Field(default_factory=dict)
