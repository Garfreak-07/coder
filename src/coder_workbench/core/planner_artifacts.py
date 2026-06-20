from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


RiskLevel = Literal["low", "medium", "high"]
ExecutionStatus = Literal["completed", "blocked", "failed"]
TestStatus = Literal["pass", "fail", "blocked"]
PlannerNextAction = Literal["continue", "ask_human", "finish", "stop"]
ConfidenceLevel = Literal["low", "medium", "high"]
PlanStatus = Literal["pending", "running", "completed", "partial_failed", "blocked", "failed"]
PlannerArtifactType = Literal[
    "run_contract",
    "planner_order",
    "execution_result",
    "test_result",
    "planner_decision",
    "round_summary",
]


class PlannerArtifactBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str | None = None
    artifact_type: PlannerArtifactType


class OptionalMergeIndexedArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    merge_index: int | None = Field(default=None, ge=1)

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_order_index(cls, data: Any) -> Any:
        if not isinstance(data, dict) or "order_index" not in data:
            return data
        migrated = dict(data)
        order_index = migrated.pop("order_index")
        if "merge_index" in migrated and migrated["merge_index"] != order_index:
            raise ValueError("merge_index and legacy order_index must match when both are provided")
        migrated.setdefault("merge_index", order_index)
        return migrated


class RequiredMergeIndexedArtifact(OptionalMergeIndexedArtifact):
    merge_index: int = Field(ge=1)


class ScopeContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed_paths: list[str] = Field(default_factory=list)
    forbidden_paths: list[str] = Field(default_factory=list)


class LoopPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_auto_rounds: int = Field(default=3, ge=0, le=20)
    user_can_override: bool = True


class RiskPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    planner_is_risk_judge: bool = True
    high_risk_requires_human: bool = True
    low_risk_auto_continue: bool = True


class ExecutionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    executor_can_modify_files: bool = True
    executor_cannot_ask_human: bool = True
    executor_must_follow_planner_order: bool = True


class TestPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_mode: str = "model_review_and_optional_command"
    tester_cannot_ask_human: bool = True


class RunContractArtifact(PlannerArtifactBase):
    artifact_type: Literal["run_contract"] = "run_contract"
    user_goal: str
    done_criteria: list[str] = Field(default_factory=list)
    scope: ScopeContract = Field(default_factory=ScopeContract)
    loop_policy: LoopPolicy = Field(default_factory=LoopPolicy)
    risk_policy: RiskPolicy = Field(default_factory=RiskPolicy)
    execution_policy: ExecutionPolicy = Field(default_factory=ExecutionPolicy)
    test_policy: TestPolicy = Field(default_factory=TestPolicy)
    human_agreements: list[str] = Field(default_factory=list)


class PlannerOrderWorkItem(RequiredMergeIndexedArtifact):
    work_item_id: str
    assignee_agent_id: str
    task_summary: str
    depends_on: list[str] = Field(default_factory=list)
    tester_agent_ids: list[str] = Field(default_factory=list)


class PlannerOrderPlanGraph(BaseModel):
    model_config = ConfigDict(extra="forbid")

    work_items: list[PlannerOrderWorkItem]
    final_tester_agent_id: str | None = None


class PlannerOrderArtifact(PlannerArtifactBase):
    artifact_type: Literal["planner_order"] = "planner_order"
    round: int = Field(default=1, ge=1)
    round_goal: str
    plan_graph: PlannerOrderPlanGraph | None = None
    instructions_for_executor: list[str] = Field(default_factory=list)
    allowed_actions: list[str] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=list)
    target_files_or_outputs: list[str] = Field(default_factory=list)
    expected_outputs: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = "low"
    requires_human_confirmation: bool = False
    tester_instructions: list[str] = Field(default_factory=list)
    stop_and_return_to_planner_when: list[str] = Field(default_factory=list)


class ExecutionResultArtifact(PlannerArtifactBase, OptionalMergeIndexedArtifact):
    artifact_type: Literal["execution_result"] = "execution_result"
    round: int = Field(default=1, ge=1)
    work_item_id: str | None = None
    agent_id: str | None = None
    status: ExecutionStatus
    summary: str
    proposed_changes: list[dict[str, Any]] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)
    created_files: list[str] = Field(default_factory=list)
    deleted_files: list[str] = Field(default_factory=list)
    patch_refs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    unexpected_issues: list[str] = Field(default_factory=list)
    out_of_contract: bool = False
    needs_planner_decision: bool = False
    tester_notes: list[str] = Field(default_factory=list)


class TestIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    severity: RiskLevel = "low"
    evidence_ref: str | None = None


class TestResultArtifact(PlannerArtifactBase, OptionalMergeIndexedArtifact):
    artifact_type: Literal["test_result"] = "test_result"
    round: int = Field(default=1, ge=1)
    work_item_id: str | None = None
    tester_agent_id: str | None = None
    status: TestStatus
    summary: str
    evidence: list[str] = Field(default_factory=list)
    issues: list[TestIssue] = Field(default_factory=list)
    remaining_work: list[str] = Field(default_factory=list)
    confidence: ConfidenceLevel = "medium"
    check_commands: list[str] = Field(default_factory=list)
    check_outputs_ref: str | None = None


class PlannerDecisionArtifact(PlannerArtifactBase):
    artifact_type: Literal["planner_decision"] = "planner_decision"
    round: int = Field(default=1, ge=1)
    task_done: bool
    next_action: PlannerNextAction
    risk_level: RiskLevel = "low"
    requires_human_confirmation: bool = False
    reason: str
    next_round_goal: str = ""
    remaining_auto_rounds: int = Field(default=0, ge=0, le=20)
    human_message: str | None = None


class RoundSummaryItem(RequiredMergeIndexedArtifact):
    work_item_id: str
    status: str
    summary: str
    refs: list[str] = Field(default_factory=list)


class RoundSummaryArtifact(PlannerArtifactBase):
    artifact_type: Literal["round_summary"] = "round_summary"
    round: int = Field(default=1, ge=1)
    planner_order_summary: str = ""
    execution_summary: str = ""
    test_summary: str = ""
    planner_decision_summary: str = ""
    planner_order_ref: str | None = None
    plan_status: PlanStatus | None = None
    completed_count: int = Field(default=0, ge=0)
    failed_count: int = Field(default=0, ge=0)
    blocked_count: int = Field(default=0, ge=0)
    ordered_state: list[RoundSummaryItem] = Field(default_factory=list)
    important_refs: list[str] = Field(default_factory=list)
    carry_forward_constraints: list[str] = Field(default_factory=list)
    remaining_work: list[str] = Field(default_factory=list)


PLANNER_ARTIFACT_MODELS: dict[str, type[PlannerArtifactBase]] = {
    "run_contract": RunContractArtifact,
    "planner_order": PlannerOrderArtifact,
    "execution_result": ExecutionResultArtifact,
    "test_result": TestResultArtifact,
    "planner_decision": PlannerDecisionArtifact,
    "round_summary": RoundSummaryArtifact,
}


def planner_artifact_summary(artifact: dict) -> dict:
    artifact_type = str(artifact.get("artifact_type") or "")
    if artifact_type == "run_contract":
        scope = artifact.get("scope") or {}
        loop_policy = artifact.get("loop_policy") or {}
        return {
            "user_goal": artifact.get("user_goal"),
            "done_criteria": len(artifact.get("done_criteria", [])),
            "allowed_paths": scope.get("allowed_paths", []),
            "forbidden_paths": scope.get("forbidden_paths", []),
            "max_auto_rounds": loop_policy.get("max_auto_rounds"),
        }
    if artifact_type == "planner_order":
        plan_graph = artifact.get("plan_graph") or {}
        return {
            "round": artifact.get("round"),
            "round_goal": artifact.get("round_goal"),
            "risk_level": artifact.get("risk_level"),
            "requires_human_confirmation": artifact.get("requires_human_confirmation"),
            "instructions": len(artifact.get("instructions_for_executor", [])),
            "expected_outputs": artifact.get("expected_outputs", []),
            "work_items": len(plan_graph.get("work_items", [])),
            "final_tester_agent_id": plan_graph.get("final_tester_agent_id"),
        }
    if artifact_type == "execution_result":
        return {
            "round": artifact.get("round"),
            "work_item_id": artifact.get("work_item_id"),
            "merge_index": artifact.get("merge_index"),
            "agent_id": artifact.get("agent_id"),
            "status": artifact.get("status"),
            "summary": artifact.get("summary"),
            "proposed_changes": len(artifact.get("proposed_changes", [])),
            "changed_files": artifact.get("changed_files", []),
            "unexpected_issues": len(artifact.get("unexpected_issues", [])),
            "needs_planner_decision": artifact.get("needs_planner_decision"),
        }
    if artifact_type == "test_result":
        return {
            "round": artifact.get("round"),
            "work_item_id": artifact.get("work_item_id"),
            "merge_index": artifact.get("merge_index"),
            "tester_agent_id": artifact.get("tester_agent_id"),
            "status": artifact.get("status"),
            "summary": artifact.get("summary"),
            "issues": len(artifact.get("issues", [])),
            "remaining_work": artifact.get("remaining_work", []),
            "confidence": artifact.get("confidence"),
        }
    if artifact_type == "planner_decision":
        return {
            "round": artifact.get("round"),
            "task_done": artifact.get("task_done"),
            "next_action": artifact.get("next_action"),
            "risk_level": artifact.get("risk_level"),
            "remaining_auto_rounds": artifact.get("remaining_auto_rounds"),
            "reason": artifact.get("reason"),
        }
    if artifact_type == "round_summary":
        return {
            "round": artifact.get("round"),
            "planner_order_summary": artifact.get("planner_order_summary"),
            "execution_summary": artifact.get("execution_summary"),
            "test_summary": artifact.get("test_summary"),
            "decision_summary": artifact.get("planner_decision_summary"),
            "plan_status": artifact.get("plan_status"),
            "ordered_state": len(artifact.get("ordered_state", [])),
            "completed_count": artifact.get("completed_count"),
            "failed_count": artifact.get("failed_count"),
            "blocked_count": artifact.get("blocked_count"),
            "remaining_work": artifact.get("remaining_work", []),
        }
    return {}
