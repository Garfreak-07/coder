from __future__ import annotations

import re
from typing import Any, Callable

from coder_workbench.agent_graph.schema import AgentTaskEnvelope, WorkItem
from coder_workbench.agent_harness.execution_memory import ExecutionRunMemory
from coder_workbench.agent_harness.execution_verification import (
    blocked_from_verification_failure,
    ensure_execution_verification,
    verification_failed,
)
from coder_workbench.core.artifacts import validate_artifact


ExecutePayload = Callable[[], dict[str, Any]]
RepairPayload = Callable[[dict[str, Any]], dict[str, Any]]


class ExecutionLoop:
    def __init__(
        self,
        *,
        execute_payload: ExecutePayload | None = None,
        repair_payload: RepairPayload | None = None,
    ) -> None:
        self.execute_payload = execute_payload
        self.repair_payload = repair_payload

    def run(
        self,
        *,
        item: WorkItem,
        envelope: AgentTaskEnvelope,
        action_gateway: Any | None = None,
        run_context: Any | None = None,
        model: Any | None = None,
        execution_memory: ExecutionRunMemory | None = None,
        emit: Any | None = None,
    ) -> dict[str, Any]:
        memory = execution_memory or ExecutionRunMemory()
        _emit(emit, "execution_loop.inspect.started", "Execution inspect stage started", work_item_id=item.work_item_id)
        if _context_missing(envelope):
            artifact = _blocked_payload(
                item,
                envelope,
                "Coding context was insufficient for this work item.",
                "context_missing",
            )
            memory.blockers.append({"work_item_id": item.work_item_id, "blocker_type": "context_missing"})
            _emit(emit, "execution_loop.inspect.blocked", artifact["summary"], work_item_id=item.work_item_id)
            return validate_artifact(artifact, expected_type="execution_result")

        _emit(emit, "execution_loop.execute.started", "Execution execute stage started", work_item_id=item.work_item_id)
        payload = self.execute_payload() if self.execute_payload is not None else _mock_completed_payload(item, envelope)
        payload = _force_execution_fields(payload, item=item, envelope=envelope)

        _emit(emit, "execution_loop.verify.started", "Execution verify stage started", work_item_id=item.work_item_id)
        artifact = ensure_execution_verification(payload)
        if verification_failed(artifact):
            _emit(emit, "execution_loop.repair.started", "Execution verification repair started", work_item_id=item.work_item_id)
            repaired = self.repair_payload(artifact) if self.repair_payload is not None else None
            if repaired is not None:
                repaired = _force_execution_fields(repaired, item=item, envelope=envelope)
                artifact = ensure_execution_verification(repaired)
                verification = dict(artifact.get("verification") or {})
                verification["repair_attempted"] = True
                verification["repair_summary"] = "Execution self-repair was attempted after verification failure."
                artifact["verification"] = verification
            if verification_failed(artifact):
                artifact = blocked_from_verification_failure(
                    artifact,
                    repair_attempted=True,
                    repair_summary="Execution self-repair did not produce passing verification.",
                )
            _emit(emit, "execution_loop.repair.completed", "Execution verification repair completed", work_item_id=item.work_item_id)

        validated = validate_artifact(artifact, expected_type="execution_result")
        memory.evidence_refs.extend(validated.get("verification", {}).get("evidence_refs", []))
        if validated["status"] == "blocked":
            memory.blockers.append(
                {
                    "work_item_id": item.work_item_id,
                    "blocker_type": validated.get("blocker_type"),
                    "summary": validated.get("summary"),
                }
            )
        _emit(emit, "execution_loop.completed", "Execution loop completed", work_item_id=item.work_item_id, status=validated["status"])
        return validated


def _context_missing(envelope: AgentTaskEnvelope) -> bool:
    packet = envelope.coding_context_packet
    if not isinstance(packet, dict) or not packet:
        return False
    included_files = packet.get("included_files")
    return isinstance(included_files, list) and not included_files and _task_mentions_file(envelope)


def _task_mentions_file(envelope: AgentTaskEnvelope) -> bool:
    texts = [envelope.task_summary, *envelope.constraints, *envelope.upstream_refs]
    return any(_FILE_HINT_RE.search(text) for text in texts if text)


_FILE_HINT_RE = re.compile(r"(?:^|\s)(?:[\w.-]+[\\/][\w./\\-]+|[\w./\\-]+\.(?:py|ts|tsx|js|jsx|json|md|txt|toml|yaml|yml|css|html|sql))(?:\s|$|[.,;:])")


def _mock_completed_payload(item: WorkItem, envelope: AgentTaskEnvelope) -> dict[str, Any]:
    return {
        "artifact_type": "execution_result",
        "round": envelope.round,
        "work_item_id": item.work_item_id,
        "merge_index": item.merge_index,
        "agent_id": item.assignee_agent_id,
        "status": "completed",
        "summary": "ExecutionLoop mock completed a dry-run execution.",
        "outputs": envelope.upstream_refs or [f"execution:{item.work_item_id}:dry-run"],
        "no_op_rationale": "Mock execution did not mutate files.",
    }


def _blocked_payload(item: WorkItem, envelope: AgentTaskEnvelope, summary: str, blocker_type: str) -> dict[str, Any]:
    return {
        "artifact_type": "execution_result",
        "round": envelope.round,
        "work_item_id": item.work_item_id,
        "merge_index": item.merge_index,
        "agent_id": item.assignee_agent_id,
        "status": "blocked",
        "summary": summary,
        "unexpected_issues": [blocker_type],
        "remaining_work": [summary],
        "needs_planner_decision": True,
        "blocker_type": blocker_type,
        "continue_without_human_possible": blocker_type == "context_missing",
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
    }


def _force_execution_fields(payload: dict[str, Any], *, item: WorkItem, envelope: AgentTaskEnvelope) -> dict[str, Any]:
    forced = dict(payload)
    forced.update(
        {
            "artifact_type": "execution_result",
            "round": envelope.round,
            "work_item_id": item.work_item_id,
            "merge_index": item.merge_index,
            "agent_id": item.assignee_agent_id,
        }
    )
    return forced


def _emit(emit: Any | None, event_type: str, message: str, **payload: Any) -> None:
    if emit is not None:
        emit(event_type, message, **{key: value for key, value in payload.items() if value is not None})
