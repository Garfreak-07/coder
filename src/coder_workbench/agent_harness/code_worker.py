from __future__ import annotations

from typing import Any

from coder_workbench.agent_graph.artifacts import graph_artifact_id
from coder_workbench.agent_graph.repair import parse_json_object
from coder_workbench.agent_graph.schema import AgentTaskEnvelope, ExecutionRecord, WorkItem
from coder_workbench.agent_harness.repair import ArtifactRepairService
from coder_workbench.agent_harness.self_check import ExecutorSelfChecker, harness_self_check_enabled
from coder_workbench.core.artifacts import ArtifactValidationError, validate_artifact

from .base import AgentHarness
from .policies import code_worker_policy


class CodeWorkerHarness(AgentHarness):
    def __init__(self, *, model: Any | None = None, enable_self_check: bool | None = None) -> None:
        super().__init__(policy=code_worker_policy())
        self.model = model
        self.enable_self_check = harness_self_check_enabled(enable_self_check)

    def create_execution_result(
        self,
        *,
        item: WorkItem,
        envelope: AgentTaskEnvelope,
        coding_context_packet: dict[str, Any] | None = None,
        emit: Any | None = None,
        prompt: str | None = None,
    ) -> ExecutionRecord:
        payload = self._payload_from_model_or_mock(
            item=item,
            envelope=envelope,
            coding_context_packet=coding_context_packet,
            emit=emit,
            prompt=prompt,
        )
        if self.enable_self_check:
            checked = ExecutorSelfChecker().check(
                payload,
                item=item,
                envelope=envelope,
                model=self.model,
                emit=emit,
            )
            artifact = checked.artifact
            return ExecutionRecord(
                work_item_id=item.work_item_id,
                merge_index=item.merge_index,
                agent_id=item.assignee_agent_id,
                status=artifact["status"],
                execution_summary=artifact["summary"],
                execution_result_ref=graph_artifact_id("execution_result", item.work_item_id),
                artifact_payload=artifact,
            )
        payload = _with_forced_fields(
            payload,
            {
                "artifact_type": "execution_result",
                "round": envelope.round,
                "work_item_id": item.work_item_id,
                "merge_index": item.merge_index,
                "agent_id": item.assignee_agent_id,
            },
        )
        try:
            artifact = validate_artifact(payload, expected_type="execution_result")
        except ArtifactValidationError:
            artifact = _blocked_payload(item, envelope.round, "Executor output failed schema validation after one repair.")
        return ExecutionRecord(
            work_item_id=item.work_item_id,
            merge_index=item.merge_index,
            agent_id=item.assignee_agent_id,
            status=artifact["status"],
            execution_summary=artifact["summary"],
            execution_result_ref=graph_artifact_id("execution_result", item.work_item_id),
            artifact_payload=artifact,
        )

    def _payload_from_model_or_mock(
        self,
        *,
        item: WorkItem,
        envelope: AgentTaskEnvelope,
        coding_context_packet: dict[str, Any] | None,
        emit: Any | None,
        prompt: str | None,
    ) -> dict[str, Any]:
        if not self.model:
            if coding_context_packet is not None and not coding_context_packet.get("included_files") and item.task_summary:
                return _blocked_payload(item, envelope.round, "Coding context was insufficient for this work item.")
            return {
                "artifact_type": "execution_result",
                "round": envelope.round,
                "status": "completed",
                "summary": "CodeWorkerHarness mock completed a dry-run execution.",
                "proposed_changes": [],
                "changed_files": [],
                "created_files": [],
                "deleted_files": [],
                "patch_refs": [],
                "outputs": envelope.upstream_refs,
                "unexpected_issues": [],
                "out_of_contract": False,
                "needs_planner_decision": False,
                "tester_notes": ["No real file mutation was performed in mock mode."],
            }
        _emit(
            emit,
            "agent_graph.agent_call.started",
            "AgentGraph model call started",
            agent_id=item.assignee_agent_id,
            artifact_type="execution_result",
            work_item_id=item.work_item_id,
            merge_index=item.merge_index,
        )
        response = self.model.invoke(prompt or _executor_prompt(item, envelope, coding_context_packet))
        content = str(getattr(response, "content", response))
        payload = parse_json_object(content)
        if payload is not None:
            try:
                artifact = validate_artifact(payload, expected_type="execution_result")
                _emit(
                    emit,
                    "agent_graph.agent_call.completed",
                    "AgentGraph model call completed",
                    agent_id=item.assignee_agent_id,
                    artifact_type="execution_result",
                    work_item_id=item.work_item_id,
                    merge_index=item.merge_index,
                )
                return artifact
            except ArtifactValidationError as exc:
                _emit_schema_failed(emit, item, exc.errors)
        else:
            _emit_schema_failed(emit, item, [{"loc": ["response"], "msg": "model output was not a JSON object"}])
        repaired = ArtifactRepairService().repair_once(
            self.model,
            expected_type="execution_result",
            invalid_output=content,
            agent_id=item.assignee_agent_id,
            emit=emit,
            work_item_id=item.work_item_id,
            merge_index=item.merge_index,
            schema_notes="Return a valid execution_result JSON object.",
        )
        if repaired is not None:
            return repaired
        return _blocked_payload(item, envelope.round, "Executor output did not match execution_result schema after one repair.")


def _emit_schema_failed(emit: Any | None, item: WorkItem, errors: list[dict[str, Any]]) -> None:
    _emit(
        emit,
        "agent_graph.agent_call.schema_failed",
        "AgentGraph artifact schema validation failed",
        agent_id=item.assignee_agent_id,
        artifact_type="execution_result",
        work_item_id=item.work_item_id,
        merge_index=item.merge_index,
        schema_errors=errors[:8],
    )


def _emit(emit: Any | None, event_type: str, message: str, **payload: Any) -> None:
    if emit is not None:
        emit(event_type, message, **{key: value for key, value in payload.items() if value is not None})


def _executor_prompt(item: WorkItem, envelope: AgentTaskEnvelope, coding_context_packet: dict[str, Any] | None) -> str:
    return "\n\n".join(
        [
            "Return JSON only with artifact_type='execution_result'.",
            "Do not ask the human. Use proposed_changes for file edits.",
            f"Work item: {item.model_dump(mode='json')}",
            f"Agent task envelope: {envelope.model_dump(mode='json')}",
            f"Coding context packet: {coding_context_packet or {}}",
        ]
    )


def _blocked_payload(item: WorkItem, round_number: int, summary: str) -> dict[str, Any]:
    schema_blocker = "schema" in summary.lower()
    return {
        "artifact_type": "execution_result",
        "round": round_number,
        "work_item_id": item.work_item_id,
        "merge_index": item.merge_index,
        "agent_id": item.assignee_agent_id,
        "status": "blocked",
        "summary": summary,
        "unexpected_issues": ["context_or_schema_blocker"],
        "needs_planner_decision": True,
        "blocker_type": "schema_validation_failed" if schema_blocker else "context_missing",
        "planner_question": (
            "Executor output failed schema validation. Should Planner retry, reassign, or ask the user?"
            if schema_blocker
            else "Should Planner provide more context, retry, or replan this work item?"
        ),
        "candidate_options": [],
        "continue_without_human_possible": not schema_blocker,
    }


def _with_forced_fields(payload: dict[str, Any], forced: dict[str, Any]) -> dict[str, Any]:
    merged = dict(payload)
    merged.update(forced)
    return merged
