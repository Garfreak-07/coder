from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


RouterSource = Literal[
    "native_repo",
    "run_evidence",
    "direct_memory",
    "hybrid_rag",
    "clarify_user",
    "none",
]

RouterMode = Literal["planning_chat", "workflow_supervisor", "task_execution"]


class RetrievalIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent_type: Literal[
        "code_fact",
        "runtime_fact",
        "code_modification",
        "project_memory",
        "external_docs",
        "user_notes",
        "prior_run_context",
        "planning",
        "ambiguous",
    ] = "ambiguous"

    needs_code_fact: bool = False
    needs_current_file_state: bool = False
    needs_runtime_evidence: bool = False
    needs_external_docs: bool = False
    needs_project_memory: bool = False
    needs_user_notes: bool = False
    needs_prior_run_context: bool = False
    query_is_code_like: bool = False

    confidence: Literal["low", "medium", "high"] = "medium"
    reason: str = "deterministic retrieval intent heuristic"


class ContextRetrievalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    use_repo_discovery: bool = False
    use_repo_search: bool = False
    use_repo_read: bool = False
    use_rag: bool = False
    rag_is_hint_only: bool = True
    requires_repo_verification: bool = False
    initial_source: RouterSource = "none"
    selected_sources: list[RouterSource] = Field(default_factory=list)
    reason: str


class RouterRoleProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: RouterMode

    default_sources: list[RouterSource]
    allowed_sources: list[RouterSource]

    allowed_memory_scopes: list[str]
    allowed_contexts: list[str]

    rag_first_allowed: bool
    repo_verification_required_for_code_claims: bool

    can_ask_user: bool
    can_write_files: bool
    can_run_commands: bool

    max_repo_evidence_tokens: int = Field(ge=0)
    max_run_evidence_tokens: int = Field(ge=0)
    max_rag_hint_tokens: int = Field(ge=0)


class AgenticContextRouterState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: RouterMode
    query: str
    rewritten_query: str | None = None

    intent: RetrievalIntent | None = None
    selected_source: RouterSource = "none"
    initial_source: RouterSource = "none"

    repo_evidence: list[dict[str, Any]] = Field(default_factory=list)
    repo_evidence_refs: list[str] = Field(default_factory=list)

    run_evidence: list[dict[str, Any]] = Field(default_factory=list)
    run_evidence_refs: list[str] = Field(default_factory=list)

    knowledge_hints: list[dict[str, Any]] = Field(default_factory=list)
    knowledge_refs: list[str] = Field(default_factory=list)

    memory_cards: list[dict[str, Any]] = Field(default_factory=list)
    memory_refs: list[str] = Field(default_factory=list)

    retrieval_grade: Literal["none", "weak", "partial", "sufficient"] = "none"
    requires_repo_verification: bool = False

    iterations: int = 0
    max_iterations: int = 3

    route_trace: list[dict[str, Any]] = Field(default_factory=list)
    stop_reason: str | None = None


__all__ = [
    "AgenticContextRouterState",
    "ContextRetrievalDecision",
    "RetrievalIntent",
    "RouterMode",
    "RouterRoleProfile",
    "RouterSource",
]
