from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Literal

from coder_workbench.agent_graph.schema import AgentTaskEnvelope, WorkItem
from coder_workbench.agent_harness.artifact_repair_pipeline import (
    ArtifactRepairPipeline,
    RepairContext,
)
from coder_workbench.agent_harness.execution_verification import ensure_blocked_contract
from coder_workbench.core.artifacts import ArtifactValidationError, validate_artifact


SelfCheckStatus = Literal["ok", "blocked"]


@dataclass(frozen=True)
class SelfCheckResult:
    status: SelfCheckStatus
    artifact: dict[str, Any]
    issues: list[str] = field(default_factory=list)


class ExecutorSelfChecker:
    def __init__(self, repair_pipeline: ArtifactRepairPipeline | None = None) -> None:
        self.repair_pipeline = repair_pipeline or ArtifactRepairPipeline()

    def check(
        self,
        payload: dict[str, Any],
        *,
        item: WorkItem,
        envelope: AgentTaskEnvelope,
        model: Any | None = None,
        emit: Any | None = None,
    ) -> SelfCheckResult:
        issues = _executor_consistency_issues(payload, item=item, envelope=envelope)
        if issues:
            artifact = _blocked_execution(item, envelope, "; ".join(issues))
            return SelfCheckResult(status="blocked", artifact=artifact, issues=issues)
        patched = dict(payload)
        patched.update(
            {
                "artifact_type": "execution_result",
                "round": envelope.round,
                "work_item_id": item.work_item_id,
                "merge_index": item.merge_index,
                "agent_id": item.assignee_agent_id,
            }
        )
        outcome = self.repair_pipeline.repair(
            expected_type="execution_result",
            invalid_output=str(payload),
            parsed_payload=patched,
            model=model,
            context=RepairContext(
                agent_id=item.assignee_agent_id,
                work_item_id=item.work_item_id,
                merge_index=item.merge_index,
                round_number=envelope.round,
                emit=emit,
                schema_notes="Return a valid execution_result JSON object with verification.",
            ),
        )
        if outcome.artifact is None:
            artifact = _blocked_execution(item, envelope, "Executor self-check could not produce a valid artifact.")
            return SelfCheckResult(status="blocked", artifact=artifact, issues=["self_check_failed"])
        issues.extend(_executor_artifact_issues(outcome.artifact))
        if issues:
            artifact = _blocked_execution(item, envelope, "; ".join(issues))
            return SelfCheckResult(status="blocked", artifact=artifact, issues=issues)
        return SelfCheckResult(status="ok", artifact=outcome.artifact, issues=[])


def harness_self_check_enabled(value: bool | None = None) -> bool:
    if value is not None:
        return bool(value)
    return str(os.getenv("CODER_ENABLE_HARNESS_SELF_CHECK") or "").strip().lower() in {"1", "true", "yes", "on"}


def _executor_consistency_issues(payload: dict[str, Any], *, item: WorkItem, envelope: AgentTaskEnvelope) -> list[str]:
    issues: list[str] = []
    if payload.get("work_item_id") not in {None, "", item.work_item_id}:
        issues.append("execution_result work_item_id does not match assigned WorkItem")
    if payload.get("merge_index") not in {None, item.merge_index}:
        issues.append("execution_result merge_index does not match assigned WorkItem")
    if payload.get("agent_id") not in {None, "", item.assignee_agent_id, envelope.assigned_agent_id}:
        issues.append("execution_result agent_id does not match assigned agent")
    if payload.get("human_message") or payload.get("ask_human"):
        issues.append("executor artifact must not include a human prompt")
    return issues


def _executor_artifact_issues(artifact: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    status = artifact.get("status")
    verification = artifact.get("verification") if isinstance(artifact.get("verification"), dict) else {}
    verification_status = verification.get("status")
    if status not in {"completed", "blocked"}:
        issues.append("execution_result status must be completed or blocked")
    if status == "completed" and not _has_completion_signal(artifact):
        issues.append("completed execution_result must include evidence or no_op_rationale")
    if status == "blocked":
        if not artifact.get("blocker_type"):
            issues.append("blocked execution_result must include blocker_type")
        if not _has_blocked_diagnostic(artifact):
            issues.append("blocked execution_result must include decision-useful diagnostics")
    if verification_status in {"fail", "blocked"} and status != "blocked":
        issues.append("verification fail/blocked requires execution_result status blocked")
    if verification_status == "skipped" and not verification.get("no_check_rationale") and not verification.get("evidence_refs"):
        issues.append("verification skipped requires no_check_rationale or evidence_refs")
    if artifact.get("proposed_changes") and not isinstance(artifact.get("patch_refs"), list):
        issues.append("execution_result patch_refs must be a list when proposed_changes are present")
    try:
        validate_artifact(artifact, expected_type="execution_result")
    except ArtifactValidationError as exc:
        issues.append(f"execution_result schema invalid: {exc}")
    return issues


def _blocked_execution(item: WorkItem, envelope: AgentTaskEnvelope, summary: str) -> dict[str, Any]:
    return validate_artifact(
        ensure_blocked_contract({
            "artifact_type": "execution_result",
            "round": envelope.round,
            "work_item_id": item.work_item_id,
            "merge_index": item.merge_index,
            "agent_id": item.assignee_agent_id,
            "status": "blocked",
            "summary": summary,
            "unexpected_issues": ["self_check_failed"],
            "remaining_work": [summary],
            "needs_planner_decision": True,
            "blocker_type": "schema_validation_failed",
            "continue_without_human_possible": False,
            "verification": {
                "status": "blocked",
                "checks_run": [],
                "evidence_refs": [],
                "confidence": "low",
                "remaining_work": [summary],
                "no_check_rationale": None,
                "repair_attempted": False,
                "repair_summary": None,
            },
        }),
        expected_type="execution_result",
    )


def _has_completion_signal(artifact: dict[str, Any]) -> bool:
    verification = artifact.get("verification") if isinstance(artifact.get("verification"), dict) else {}
    return any(
        [
            artifact.get("changed_files"),
            artifact.get("created_files"),
            artifact.get("deleted_files"),
            artifact.get("patch_refs"),
            artifact.get("outputs"),
            artifact.get("evidence_refs"),
            artifact.get("no_op_rationale"),
            verification.get("checks_run"),
            verification.get("evidence_refs"),
            verification.get("no_check_rationale") if verification.get("status") == "skipped" else None,
        ]
    )


def _has_blocked_diagnostic(artifact: dict[str, Any]) -> bool:
    verification = artifact.get("verification") if isinstance(artifact.get("verification"), dict) else {}
    return any(
        [
            artifact.get("unexpected_issues"),
            artifact.get("attempted_actions"),
            artifact.get("evidence_refs"),
            artifact.get("remaining_work"),
            verification.get("remaining_work"),
            verification.get("evidence_refs"),
            verification.get("checks_run"),
            artifact.get("planner_question"),
            artifact.get("candidate_options"),
            artifact.get("planner_options"),
        ]
    )
