from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


RiskLevel = Literal["low", "medium", "high"]
ExecutionStatus = Literal["completed", "blocked"]
VerificationStatus = Literal["pass", "fail", "blocked", "skipped"]
ConfidenceLevel = Literal["low", "medium", "high"]
FinalReportStatus = Literal["completed", "blocked", "failed", "cancelled"]
BlockerType = Literal[
    "test_failed",
    "command_failed",
    "schema_validation_failed",
    "command_unavailable",
    "missing_dependency",
    "missing_file",
    "scope_violation",
    "risk_path_blocked",
    "permission_boundary",
    "missing_secret",
    "network_required",
    "external_account_required",
    "timeout",
    "context_missing",
    "tool_unavailable",
    "sandbox_unavailable",
    "unknown_error",
]
PlannerRecommendation = Literal["replan_once", "finish"]
PlannerNextAction = Literal["continue", "finish"]
PlanStatus = Literal["pending", "running", "completed", "blocked", "interrupted"]
PlannerArtifactType = Literal[
    "project_plan_draft",
    "run_contract_draft",
    "run_contract",
    "planner_order",
    "execution_result",
    "planner_decision",
    "round_summary",
    "final_report",
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
    def accept_order_index_alias(cls, data: Any) -> Any:
        if not isinstance(data, dict) or "order_index" not in data:
            return data
        migrated = dict(data)
        order_index = migrated.pop("order_index")
        if "merge_index" in migrated and migrated["merge_index"] != order_index:
            raise ValueError("merge_index and order_index must match when both are provided")
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
    executor_can_run_check_commands: bool = True
    executor_cannot_ask_human: bool = True
    executor_must_follow_planner_order: bool = True


class ProjectPlanDraftArtifact(PlannerArtifactBase):
    artifact_type: Literal["project_plan_draft"] = "project_plan_draft"
    draft_id: str
    summary: str
    proposed_scope: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    requires_confirmation: bool = True


class RunContractDraftArtifact(PlannerArtifactBase):
    artifact_type: Literal["run_contract_draft"] = "run_contract_draft"
    draft_id: str
    user_goal: str
    workflow_id: str
    planner_agent_id: str
    success_criteria: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    selected_knowledge_pack_ids: list[str] = Field(default_factory=list)
    selected_skill_pack_ids: list[str] = Field(default_factory=list)
    selected_memory_pack_ids: list[str] = Field(default_factory=list)
    requires_confirmation: bool = True


class RunContractArtifact(PlannerArtifactBase):
    artifact_type: Literal["run_contract"] = "run_contract"
    user_goal: str
    done_criteria: list[str] = Field(default_factory=list)
    scope: ScopeContract = Field(default_factory=ScopeContract)
    loop_policy: LoopPolicy = Field(default_factory=LoopPolicy)
    risk_policy: RiskPolicy = Field(default_factory=RiskPolicy)
    execution_policy: ExecutionPolicy = Field(default_factory=ExecutionPolicy)
    human_agreements: list[str] = Field(default_factory=list)


class PlannerOrderWorkItem(RequiredMergeIndexedArtifact):
    work_item_id: str
    assignee_agent_id: str
    task_summary: str
    depends_on: list[str] = Field(default_factory=list)


class PlannerOrderPlanGraph(BaseModel):
    model_config = ConfigDict(extra="forbid")

    work_items: list[PlannerOrderWorkItem]


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
    stop_and_return_to_planner_when: list[str] = Field(default_factory=list)


class PlannerOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    option_id: str
    summary: str
    risk_level: RiskLevel = "low"
    requires_human: bool = False


class RecoveryAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str
    result: str


class ConstraintBoundary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    within_scope: bool = True
    requires_secret: bool = False
    requires_network: bool = False
    requires_external_account: bool = False
    requires_destructive_action: bool = False
    requires_out_of_scope_write: bool = False


class VerificationCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    check_id: str | None = None
    kind: Literal["command", "static", "model", "skipped"] = "model"
    command: str | None = None
    status: VerificationStatus
    summary: str = ""
    output_ref: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)


class ExecutionVerification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: VerificationStatus
    checks_run: list[VerificationCheck] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: ConfidenceLevel = "medium"
    remaining_work: list[str] = Field(default_factory=list)
    no_check_rationale: str | None = None
    repair_attempted: bool = False
    repair_summary: str | None = None

    @model_validator(mode="after")
    def require_skipped_rationale(self) -> "ExecutionVerification":
        if self.status == "skipped" and not self.no_check_rationale and not self.evidence_refs:
            raise ValueError("verification.status=skipped requires no_check_rationale or evidence_refs")
        return self


class ExecutionResultArtifact(PlannerArtifactBase, OptionalMergeIndexedArtifact):
    artifact_type: Literal["execution_result"] = "execution_result"
    round: int = Field(default=1, ge=1)
    work_item_id: str | None = None
    agent_id: str | None = None
    status: ExecutionStatus
    summary: str
    proposed_changes: list[dict[str, Any]] = Field(default_factory=list)
    requested_actions: list[dict[str, Any]] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)
    created_files: list[str] = Field(default_factory=list)
    deleted_files: list[str] = Field(default_factory=list)
    patch_refs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    attempted_actions: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    remaining_work: list[str] = Field(default_factory=list)
    unexpected_issues: list[str] = Field(default_factory=list)
    out_of_contract: bool = False
    needs_planner_decision: bool = False
    blocker_type: BlockerType | None = None
    executor_recovery_exhausted: bool | None = None
    blocker_reason: str | None = None
    blocker_fingerprint: str | None = None
    recovery_attempts: list[RecoveryAttempt] = Field(default_factory=list)
    planner_recommendation: PlannerRecommendation | None = None
    replan_goal: str | None = None
    affected_files: list[str] = Field(default_factory=list)
    constraint_boundary: ConstraintBoundary | None = None
    planner_question: str | None = None
    candidate_options: list[PlannerOption] = Field(default_factory=list)
    planner_options: list[PlannerOption] = Field(default_factory=list)
    continue_without_human_possible: bool | None = None
    no_op_rationale: str | None = None
    verification: ExecutionVerification

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_blocked_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        blocker_type = data.get("blocker_type")
        mapped = _legacy_blocker_type(str(blocker_type)) if blocker_type is not None else None
        if mapped == blocker_type:
            return data
        migrated = dict(data)
        if mapped is not None:
            migrated["blocker_type"] = mapped
        return migrated

    @model_validator(mode="after")
    def enforce_execution_semantics(self) -> "ExecutionResultArtifact":
        if self.verification.status in {"fail", "blocked"} and self.status != "blocked":
            raise ValueError("verification fail/blocked requires execution_result.status=blocked")
        if self.status == "completed" and self.verification.status not in {"pass", "skipped"}:
            raise ValueError("completed execution_result requires verification pass or skipped")
        if self.status == "completed" and not _has_completion_signal(self):
            raise ValueError("completed execution_result requires credible completion evidence or no_op_rationale")
        if self.status == "blocked":
            if self.blocker_type is None:
                raise ValueError("blocked execution_result requires blocker_type")
            if self.executor_recovery_exhausted is not True:
                raise ValueError("blocked execution_result requires executor_recovery_exhausted=true")
            if not self.blocker_reason:
                raise ValueError("blocked execution_result requires blocker_reason")
            if self.planner_recommendation is None:
                raise ValueError("blocked execution_result requires planner_recommendation")
            if not _has_blocked_next_step_signal(self):
                raise ValueError("blocked execution_result requires remaining_work, affected_files, or evidence_refs")
            if not _has_blocked_diagnostic(self):
                raise ValueError("blocked execution_result requires decision-useful diagnostics")
        return self


class PlannerDecisionArtifact(PlannerArtifactBase):
    artifact_type: Literal["planner_decision"] = "planner_decision"
    round: int = Field(default=1, ge=1)
    task_done: bool
    next_action: PlannerNextAction
    final_status: FinalReportStatus | None = None
    risk_level: RiskLevel = "low"
    requires_human_confirmation: bool = False
    reason: str
    next_round_goal: str = ""
    remaining_auto_rounds: int = Field(default=0, ge=0, le=20)
    human_message: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_next_action(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        action = data.get("next_action")
        if action == "stop":
            migrated = dict(data)
            migrated["next_action"] = "finish"
            migrated.setdefault("task_done", True)
            return migrated
        if action in {"ask_human", "blocked"}:
            migrated = dict(data)
            migrated["next_action"] = "finish"
            migrated["task_done"] = False
            migrated.setdefault("final_status", "blocked")
            migrated["requires_human_confirmation"] = False
            return migrated
        return data


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
    planner_decision_summary: str = ""
    planner_order_ref: str | None = None
    plan_status: PlanStatus | None = None
    completed_count: int = Field(default=0, ge=0)
    blocked_count: int = Field(default=0, ge=0)
    ordered_state: list[RoundSummaryItem] = Field(default_factory=list)
    important_refs: list[str] = Field(default_factory=list)
    carry_forward_constraints: list[str] = Field(default_factory=list)
    remaining_work: list[str] = Field(default_factory=list)


class FinalReportCommit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sha: str | None = None
    message: str | None = None


class FinalReportFiles(BaseModel):
    model_config = ConfigDict(extra="forbid")

    created: list[str] = Field(default_factory=list)
    modified: list[str] = Field(default_factory=list)
    deleted: list[str] = Field(default_factory=list)


class FinalReportCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: str | None = None
    status: Literal["passed", "failed", "blocked", "skipped", "unknown"]
    summary: str = ""
    output_ref: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)


class FinalReportArtifact(PlannerArtifactBase):
    artifact_type: Literal["final_report"] = "final_report"
    status: FinalReportStatus
    summary: str
    commit: FinalReportCommit | None = None
    files: FinalReportFiles = Field(default_factory=FinalReportFiles)
    checks: list[FinalReportCheck] = Field(default_factory=list)
    completed: list[str] = Field(default_factory=list)
    blocked_by: list[str] = Field(default_factory=list)
    failed_by: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


PLANNER_ARTIFACT_MODELS: dict[str, type[PlannerArtifactBase]] = {
    "project_plan_draft": ProjectPlanDraftArtifact,
    "run_contract_draft": RunContractDraftArtifact,
    "run_contract": RunContractArtifact,
    "planner_order": PlannerOrderArtifact,
    "execution_result": ExecutionResultArtifact,
    "planner_decision": PlannerDecisionArtifact,
    "round_summary": RoundSummaryArtifact,
    "final_report": FinalReportArtifact,
}


def planner_artifact_summary(artifact: dict) -> dict:
    artifact_type = str(artifact.get("artifact_type") or "")
    if artifact_type == "project_plan_draft":
        return {
            "draft_id": artifact.get("draft_id"),
            "summary": artifact.get("summary"),
            "success_criteria": len(artifact.get("success_criteria", [])),
            "risks": len(artifact.get("risks", [])),
            "requires_confirmation": artifact.get("requires_confirmation"),
        }
    if artifact_type == "run_contract_draft":
        return {
            "draft_id": artifact.get("draft_id"),
            "user_goal": artifact.get("user_goal"),
            "workflow_id": artifact.get("workflow_id"),
            "planner_agent_id": artifact.get("planner_agent_id"),
            "success_criteria": len(artifact.get("success_criteria", [])),
            "requires_confirmation": artifact.get("requires_confirmation"),
        }
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
        }
    if artifact_type == "execution_result":
        verification = artifact.get("verification") or {}
        return {
            "round": artifact.get("round"),
            "work_item_id": artifact.get("work_item_id"),
            "merge_index": artifact.get("merge_index"),
            "agent_id": artifact.get("agent_id"),
            "status": artifact.get("status"),
            "summary": artifact.get("summary"),
            "verification_status": verification.get("status"),
            "proposed_changes": len(artifact.get("proposed_changes", [])),
            "requested_actions": len(artifact.get("requested_actions", [])),
            "changed_files": artifact.get("changed_files", []),
            "unexpected_issues": len(artifact.get("unexpected_issues", [])),
            "blocker_type": artifact.get("blocker_type"),
            "needs_planner_decision": artifact.get("needs_planner_decision"),
            "continue_without_human_possible": artifact.get("continue_without_human_possible"),
            "candidate_options": len(artifact.get("candidate_options", [])),
            "planner_options": len(artifact.get("planner_options", [])),
        }
    if artifact_type == "planner_decision":
        return {
            "round": artifact.get("round"),
            "task_done": artifact.get("task_done"),
            "next_action": artifact.get("next_action"),
            "final_status": artifact.get("final_status"),
            "risk_level": artifact.get("risk_level"),
            "remaining_auto_rounds": artifact.get("remaining_auto_rounds"),
            "reason": artifact.get("reason"),
        }
    if artifact_type == "round_summary":
        return {
            "round": artifact.get("round"),
            "planner_order_summary": artifact.get("planner_order_summary"),
            "execution_summary": artifact.get("execution_summary"),
            "decision_summary": artifact.get("planner_decision_summary"),
            "plan_status": artifact.get("plan_status"),
            "ordered_state": len(artifact.get("ordered_state", [])),
            "completed_count": artifact.get("completed_count"),
            "blocked_count": artifact.get("blocked_count"),
            "remaining_work": artifact.get("remaining_work", []),
        }
    if artifact_type == "final_report":
        files = artifact.get("files") or {}
        return {
            "status": artifact.get("status"),
            "summary": artifact.get("summary"),
            "created_files": files.get("created", []),
            "modified_files": files.get("modified", []),
            "deleted_files": files.get("deleted", []),
            "checks": len(artifact.get("checks", [])),
            "completed": len(artifact.get("completed", [])),
            "blocked_by": len(artifact.get("blocked_by", [])),
            "failed_by": len(artifact.get("failed_by", [])),
            "warnings": len(artifact.get("warnings", [])),
            "evidence_refs": len(artifact.get("evidence_refs", [])),
        }
    return {}


def _has_completion_signal(artifact: ExecutionResultArtifact) -> bool:
    verification = artifact.verification
    return any(
        [
            artifact.changed_files,
            artifact.created_files,
            artifact.deleted_files,
            artifact.patch_refs,
            artifact.outputs,
            artifact.evidence_refs,
            artifact.no_op_rationale,
            verification.checks_run,
            verification.evidence_refs,
            verification.no_check_rationale if verification.status == "skipped" else None,
        ]
    )


def _has_blocked_diagnostic(artifact: ExecutionResultArtifact) -> bool:
    return any(
        [
            artifact.unexpected_issues,
            artifact.attempted_actions,
            artifact.evidence_refs,
            artifact.remaining_work,
            artifact.verification.remaining_work,
            artifact.verification.evidence_refs,
            artifact.verification.checks_run,
            artifact.planner_question,
            artifact.candidate_options,
            artifact.planner_options,
            artifact.recovery_attempts,
            artifact.blocker_reason,
        ]
    )


def _has_blocked_next_step_signal(artifact: ExecutionResultArtifact) -> bool:
    return any(
        [
            artifact.remaining_work,
            artifact.verification.remaining_work,
            artifact.affected_files,
            artifact.evidence_refs,
            artifact.verification.evidence_refs,
        ]
    )


def _legacy_blocker_type(value: str) -> str:
    return {
        "technical_blocker": "unknown_error",
        "verification_failed": "test_failed",
        "permission_blocked": "permission_boundary",
        "dependency_missing": "missing_dependency",
        "tool_error": "tool_unavailable",
        "out_of_contract": "scope_violation",
        "scope_boundary": "scope_violation",
        "risk_boundary": "risk_path_blocked",
        "unsafe_action": "risk_path_blocked",
        "patch_rejected": "risk_path_blocked",
        "transient_error_exhausted": "unknown_error",
        "ambiguity": "context_missing",
        "plan_conflict": "unknown_error",
    }.get(value, value)
