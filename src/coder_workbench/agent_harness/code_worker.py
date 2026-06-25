from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from coder_workbench.actions import ActionGateway, RunContext
from coder_workbench.agent_graph.artifacts import graph_artifact_id
from coder_workbench.agent_graph.repair import parse_json_object
from coder_workbench.agent_graph.schema import AgentTaskEnvelope, ExecutionRecord, WorkItem
from coder_workbench.agent_harness.artifact_repair_pipeline import ArtifactRepairPipeline
from coder_workbench.agent_harness.execution_loop import ExecutionLoop
from coder_workbench.agent_harness.execution_verification import ensure_execution_verification
from coder_workbench.agent_harness.execution_memory import ExecutionRunMemory
from coder_workbench.agent_harness.repair import ArtifactRepairService
from coder_workbench.agent_harness.self_check import ExecutorSelfChecker, harness_self_check_enabled
from coder_workbench.agent_harness.tool_gate import ToolGate
from coder_workbench.agent_harness.tool_loop import CodeWorkerToolLoop
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
        repo_root: str | Path = ".",
        sandbox_root: str | Path | None = None,
        scopes: list[str] | None = None,
        run_id: str | None = None,
        data: dict[str, Any] | None = None,
        action_gateway: ActionGateway | None = None,
        capability_set: dict[str, Any] | None = None,
    ) -> ExecutionRecord:
        loop_envelope = envelope
        if coding_context_packet is not None and not envelope.coding_context_packet:
            loop_envelope = envelope.model_copy(update={"coding_context_packet": coding_context_packet})
        if capability_set is not None:
            loop_envelope = loop_envelope.model_copy(update={"capability_set": capability_set})
        if _tool_loop_enabled():
            return self._create_execution_result_with_tool_loop(
                item=item,
                envelope=loop_envelope,
                emit=emit,
                prompt=prompt,
                repo_root=repo_root,
                sandbox_root=sandbox_root,
                scopes=scopes,
                run_id=run_id,
                data=data,
                action_gateway=action_gateway,
            )
        try:
            payload = ExecutionLoop(
                execute_payload=lambda: self._payload_from_model_or_mock(
                    item=item,
                    envelope=loop_envelope,
                    coding_context_packet=coding_context_packet,
                    emit=emit,
                    prompt=prompt,
                )
            ).run(
                item=item,
                envelope=loop_envelope,
                model=self.model,
                execution_memory=ExecutionRunMemory(),
                emit=emit,
            )
        except ArtifactValidationError:
            payload = _blocked_payload(item, loop_envelope.round, "Executor output failed schema validation after one repair.")
            payload = ensure_execution_verification(payload)
        if self.enable_self_check:
            checked = ExecutorSelfChecker().check(
                payload,
                item=item,
                envelope=loop_envelope,
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
        artifact = validate_artifact(ensure_execution_verification(payload), expected_type="execution_result")
        return ExecutionRecord(
            work_item_id=item.work_item_id,
            merge_index=item.merge_index,
            agent_id=item.assignee_agent_id,
            status=artifact["status"],
            execution_summary=artifact["summary"],
            execution_result_ref=graph_artifact_id("execution_result", item.work_item_id),
            artifact_payload=artifact,
        )

    def _create_execution_result_with_tool_loop(
        self,
        *,
        item: WorkItem,
        envelope: AgentTaskEnvelope,
        emit: Any | None,
        prompt: str | None,
        repo_root: str | Path,
        sandbox_root: str | Path | None,
        scopes: list[str] | None,
        run_id: str | None,
        data: dict[str, Any] | None,
        action_gateway: ActionGateway | None,
    ) -> ExecutionRecord:
        run_data = data if data is not None else {}
        gateway = action_gateway or ActionGateway()
        run_context = RunContext(
            run_id=run_id or str(run_data.get("run_id") or "code-worker-run"),
            repo_root=repo_root,
            sandbox_root=sandbox_root,
            scopes=scopes,
            data=run_data,
            item=item,
            planner_order_ref=envelope.planner_order_ref,
            upstream_refs=envelope.upstream_refs,
            user_request=envelope.task_summary,
            role="executor",
            artifact_type="execution_result",
            emit=emit,
            model=self.model,
        )
        capability_set = dict(envelope.capability_set or {})
        tool_gate = ToolGate(run_context=run_context, capability_set=capability_set)
        try:
            artifact = CodeWorkerToolLoop(
                model=self.model,
                action_gateway=gateway,
                run_context=run_context,
                tool_gate=tool_gate,
                repair_pipeline=ArtifactRepairPipeline(),
                self_checker=ExecutorSelfChecker(),
                emit=emit,
            ).run(
                item=item,
                envelope=envelope,
                prompt=prompt or _executor_prompt(item, envelope, envelope.coding_context_packet),
            )
        except ArtifactValidationError:
            artifact = validate_artifact(
                ensure_execution_verification(
                    _blocked_payload(item, envelope.round, "CodeWorker tool loop returned invalid execution_result.")
                ),
                expected_type="execution_result",
            )
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
                "outputs": envelope.upstream_refs or [f"execution:{item.work_item_id}:dry-run"],
                "unexpected_issues": [],
                "out_of_contract": False,
                "needs_planner_decision": False,
                "no_op_rationale": "No real file mutation was performed in mock mode.",
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
            _emit(
                emit,
                "agent_graph.agent_call.completed",
                "AgentGraph model call completed",
                agent_id=item.assignee_agent_id,
                artifact_type="execution_result",
                work_item_id=item.work_item_id,
                merge_index=item.merge_index,
            )
            return payload
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


def _tool_loop_enabled() -> bool:
    return str(os.getenv("CODER_ENABLE_CODE_WORKER_TOOL_LOOP") or "").strip().lower() in {"1", "true", "yes", "on"}


def _executor_prompt(item: WorkItem, envelope: AgentTaskEnvelope, coding_context_packet: dict[str, Any] | None) -> str:
    return "\n\n".join(
        [
            "Return JSON only with artifact_type='execution_result'.",
            "Do not ask the human. Use proposed_changes for file edits.",
            "Include verification with status pass, fail, blocked, or skipped.",
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


def _with_forced_fields(payload: dict[str, Any], forced: dict[str, Any]) -> dict[str, Any]:
    merged = dict(payload)
    merged.update(forced)
    return merged
