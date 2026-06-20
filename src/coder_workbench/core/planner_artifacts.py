from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


RiskLevel = Literal["low", "medium", "high"]
ExecutionStatus = Literal["completed", "blocked", "failed"]
TestStatus = Literal["pass", "fail", "blocked"]
PlannerNextAction = Literal["continue", "ask_human", "finish", "stop"]
ConfidenceLevel = Literal["low", "medium", "high"]
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


class PlannerOrderArtifact(PlannerArtifactBase):
    artifact_type: Literal["planner_order"] = "planner_order"
    round: int = Field(default=1, ge=1)
    round_goal: str
    instructions_for_executor: list[str] = Field(default_factory=list)
    allowed_actions: list[str] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=list)
    target_files_or_outputs: list[str] = Field(default_factory=list)
    expected_outputs: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = "low"
    requires_human_confirmation: bool = False
    tester_instructions: list[str] = Field(default_factory=list)
    stop_and_return_to_planner_when: list[str] = Field(default_factory=list)


class ExecutionResultArtifact(PlannerArtifactBase):
    artifact_type: Literal["execution_result"] = "execution_result"
    round: int = Field(default=1, ge=1)
    status: ExecutionStatus
    summary: str
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


class TestResultArtifact(PlannerArtifactBase):
    artifact_type: Literal["test_result"] = "test_result"
    round: int = Field(default=1, ge=1)
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


class RoundSummaryArtifact(PlannerArtifactBase):
    artifact_type: Literal["round_summary"] = "round_summary"
    round: int = Field(default=1, ge=1)
    planner_order_summary: str
    execution_summary: str
    test_summary: str
    planner_decision_summary: str
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
        return {
            "round": artifact.get("round"),
            "round_goal": artifact.get("round_goal"),
            "risk_level": artifact.get("risk_level"),
            "requires_human_confirmation": artifact.get("requires_human_confirmation"),
            "instructions": len(artifact.get("instructions_for_executor", [])),
            "expected_outputs": artifact.get("expected_outputs", []),
        }
    if artifact_type == "execution_result":
        return {
            "round": artifact.get("round"),
            "status": artifact.get("status"),
            "summary": artifact.get("summary"),
            "changed_files": artifact.get("changed_files", []),
            "unexpected_issues": len(artifact.get("unexpected_issues", [])),
            "needs_planner_decision": artifact.get("needs_planner_decision"),
        }
    if artifact_type == "test_result":
        return {
            "round": artifact.get("round"),
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
            "remaining_work": artifact.get("remaining_work", []),
        }
    return {}
