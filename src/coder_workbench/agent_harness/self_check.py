from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Literal

from coder_workbench.agent_graph.schema import AgentTaskEnvelope, WorkItem
from coder_workbench.agent_harness.artifact_repair_pipeline import (
    ArtifactRepairPipeline,
    RepairContext,
)
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
                schema_notes="Return a valid execution_result JSON object.",
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


class TesterSelfChecker:
    def __init__(self, repair_pipeline: ArtifactRepairPipeline | None = None) -> None:
        self.repair_pipeline = repair_pipeline or ArtifactRepairPipeline()

    def check(
        self,
        payload: dict[str, Any],
        *,
        item: WorkItem,
        tester_agent_id: str,
        evidence_refs: list[str],
        round_number: int,
        model: Any | None = None,
        emit: Any | None = None,
    ) -> SelfCheckResult:
        issues = _tester_consistency_issues(payload, item=item, tester_agent_id=tester_agent_id)
        if issues:
            artifact = _blocked_test(item, tester_agent_id, round_number, "; ".join(issues))
            return SelfCheckResult(status="blocked", artifact=artifact, issues=issues)
        patched = dict(payload)
        patched.update(
            {
                "artifact_type": "test_result",
                "round": round_number,
                "work_item_id": item.work_item_id,
                "merge_index": item.merge_index,
                "tester_agent_id": tester_agent_id,
            }
        )
        outcome = self.repair_pipeline.repair(
            expected_type="test_result",
            invalid_output=str(payload),
            parsed_payload=patched,
            model=model,
            context=RepairContext(
                agent_id=tester_agent_id,
                work_item_id=item.work_item_id,
                merge_index=item.merge_index,
                round_number=round_number,
                tester_agent_id=tester_agent_id,
                emit=emit,
                schema_notes="Return a valid test_result JSON object.",
            ),
        )
        if outcome.artifact is None:
            artifact = _blocked_test(item, tester_agent_id, round_number, "Tester self-check could not produce a valid artifact.")
            return SelfCheckResult(status="blocked", artifact=artifact, issues=["self_check_failed"])
        issues.extend(_tester_artifact_issues(outcome.artifact, evidence_refs=evidence_refs))
        if issues:
            artifact = _blocked_test(item, tester_agent_id, round_number, "; ".join(issues))
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
    if status in {"blocked", "failed"} and not artifact.get("unexpected_issues"):
        issues.append("blocked or failed execution_result must include unexpected_issues")
    if artifact.get("proposed_changes") and not isinstance(artifact.get("patch_refs"), list):
        issues.append("execution_result patch_refs must be a list when proposed_changes are present")
    try:
        validate_artifact(artifact, expected_type="execution_result")
    except ArtifactValidationError as exc:
        issues.append(f"execution_result schema invalid: {exc}")
    return issues


def _tester_consistency_issues(payload: dict[str, Any], *, item: WorkItem, tester_agent_id: str) -> list[str]:
    issues: list[str] = []
    if payload.get("work_item_id") not in {None, "", item.work_item_id}:
        issues.append("test_result work_item_id does not match assigned WorkItem")
    if payload.get("merge_index") not in {None, item.merge_index}:
        issues.append("test_result merge_index does not match assigned WorkItem")
    if payload.get("tester_agent_id") not in {None, "", tester_agent_id}:
        issues.append("test_result tester_agent_id does not match assigned tester")
    if payload.get("human_message") or payload.get("ask_human"):
        issues.append("tester artifact must not include a human prompt")
    return issues


def _tester_artifact_issues(artifact: dict[str, Any], *, evidence_refs: list[str]) -> list[str]:
    issues: list[str] = []
    status = artifact.get("status")
    if status not in {"pass", "fail", "blocked"}:
        issues.append("test_result status must be pass, fail, or blocked")
    if status in {"fail", "blocked"} and not artifact.get("remaining_work"):
        issues.append("failed or blocked test_result must include remaining_work")
    if evidence_refs and not artifact.get("evidence"):
        issues.append("test_result must reference upstream evidence")
    if not artifact.get("confidence"):
        issues.append("test_result confidence is required")
    try:
        validate_artifact(artifact, expected_type="test_result")
    except ArtifactValidationError as exc:
        issues.append(f"test_result schema invalid: {exc}")
    return issues


def _blocked_execution(item: WorkItem, envelope: AgentTaskEnvelope, summary: str) -> dict[str, Any]:
    return validate_artifact(
        {
            "artifact_type": "execution_result",
            "round": envelope.round,
            "work_item_id": item.work_item_id,
            "merge_index": item.merge_index,
            "agent_id": item.assignee_agent_id,
            "status": "blocked",
            "summary": summary,
            "unexpected_issues": ["self_check_failed"],
            "needs_planner_decision": True,
            "blocker_type": "schema_validation_failed",
            "continue_without_human_possible": False,
        },
        expected_type="execution_result",
    )


def _blocked_test(item: WorkItem, tester_agent_id: str, round_number: int, summary: str) -> dict[str, Any]:
    return validate_artifact(
        {
            "artifact_type": "test_result",
            "round": round_number,
            "work_item_id": item.work_item_id,
            "merge_index": item.merge_index,
            "tester_agent_id": tester_agent_id,
            "status": "blocked",
            "summary": summary,
            "remaining_work": [summary],
            "confidence": "low",
        },
        expected_type="test_result",
    )
