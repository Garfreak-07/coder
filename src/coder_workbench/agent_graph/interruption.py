from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


InterruptSeverity = Literal["low", "medium", "high"]


class GraphInterrupt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    round: int
    work_item_id: str
    merge_index: int
    agent_id: str
    blocker_type: str
    reason: str
    planner_question: str | None = None
    continue_without_human_possible: bool | None = None
    candidate_options: list[dict[str, Any]] = Field(default_factory=list)
    artifact_ref: str


INTERRUPT_BLOCKER_TYPES = {
    "ambiguity",
    "scope_boundary",
    "risk_boundary",
    "dependency_missing",
    "context_missing",
    "plan_conflict",
    "schema_validation_failed",
}


def should_interrupt_execution(artifact: dict[str, Any]) -> bool:
    if artifact.get("needs_planner_decision") is True:
        return True
    if artifact.get("out_of_contract") is True:
        return True
    if artifact.get("blocker_type") in INTERRUPT_BLOCKER_TYPES:
        return True
    return False


def build_graph_interrupt(
    *,
    round_number: int,
    artifact: dict[str, Any],
    artifact_ref: str,
) -> GraphInterrupt:
    return GraphInterrupt(
        round=round_number,
        work_item_id=str(artifact.get("work_item_id") or ""),
        merge_index=int(artifact.get("merge_index") or 1),
        agent_id=str(artifact.get("agent_id") or ""),
        blocker_type=str(artifact.get("blocker_type") or "technical_blocker"),
        reason=str(artifact.get("summary") or ""),
        planner_question=artifact.get("planner_question"),
        continue_without_human_possible=artifact.get("continue_without_human_possible"),
        candidate_options=list(artifact.get("candidate_options") or []),
        artifact_ref=artifact_ref,
    )
