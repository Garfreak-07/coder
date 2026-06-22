from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import ValidationError

from coder_workbench.agent_graph.repair import build_repair_prompt, parse_json_object
from coder_workbench.core.artifacts import ArtifactValidationError, validate_artifact


RepairStatus = Literal["ok", "blocked", "failed"]


@dataclass(frozen=True)
class RepairContext:
    agent_id: str
    work_item_id: str | None = None
    merge_index: int | None = None
    round_number: int = 1
    tester_agent_id: str | None = None
    schema_notes: str = ""
    emit: Any | None = None


@dataclass(frozen=True)
class RepairOutcome:
    status: RepairStatus
    artifact: dict[str, Any] | None
    stage: str
    repair_used: bool = False
    errors: list[dict[str, Any]] = field(default_factory=list)
    blocker_reason: str = ""


class ArtifactRepairPipeline:
    def repair(
        self,
        *,
        expected_type: str,
        invalid_output: str,
        parsed_payload: dict[str, Any] | None = None,
        model: Any | None = None,
        context: RepairContext,
    ) -> RepairOutcome:
        payload = parsed_payload if parsed_payload is not None else _raw_parse(invalid_output)
        if payload is not None:
            validated = _validate(payload, expected_type=expected_type)
            if validated.status == "ok":
                return RepairOutcome(status="ok", artifact=validated.artifact, stage="raw_parse")

            patched = _deterministic_schema_patch(
                payload,
                expected_type=expected_type,
                context=context,
            )
            patched_validated = _validate(patched, expected_type=expected_type)
            if patched_validated.status == "ok":
                return RepairOutcome(
                    status="ok",
                    artifact=patched_validated.artifact,
                    stage="deterministic_schema_patch",
                    errors=validated.errors,
                )
        else:
            validated = RepairOutcome(status="failed", artifact=None, stage="raw_parse", errors=[{"loc": ["response"], "msg": "not json"}])

        if model is not None:
            _emit(
                context.emit,
                "agent_graph.agent_call.repair_started",
                "AgentGraph artifact repair started",
                agent_id=context.agent_id,
                artifact_type=expected_type,
                work_item_id=context.work_item_id,
                merge_index=context.merge_index,
            )
            response = model.invoke(
                build_repair_prompt(
                    expected_type=expected_type,
                    invalid_output=invalid_output,
                    errors=validated.errors or [{"loc": ["artifact"], "msg": "schema validation failed"}],
                    schema_notes=context.schema_notes or f"Return a valid {expected_type} JSON object.",
                )
            )
            repaired_payload = parse_json_object(str(getattr(response, "content", response)))
            if repaired_payload is not None:
                repaired_payload = _deterministic_schema_patch(
                    repaired_payload,
                    expected_type=expected_type,
                    context=context,
                )
                repaired = _validate(repaired_payload, expected_type=expected_type)
                if repaired.status == "ok":
                    _emit(
                        context.emit,
                        "agent_graph.agent_call.repair_completed",
                        "AgentGraph artifact repair completed",
                        agent_id=context.agent_id,
                        artifact_type=expected_type,
                        work_item_id=context.work_item_id,
                        merge_index=context.merge_index,
                    )
                    return RepairOutcome(
                        status="ok",
                        artifact=repaired.artifact,
                        stage="model_repair",
                        repair_used=True,
                        errors=validated.errors,
                    )
            _emit(
                context.emit,
                "agent_graph.agent_call.repair_failed",
                "AgentGraph artifact repair failed",
                agent_id=context.agent_id,
                artifact_type=expected_type,
                work_item_id=context.work_item_id,
                merge_index=context.merge_index,
            )

        fallback = _fallback_artifact(expected_type, context)
        fallback_validated = _validate(fallback, expected_type=expected_type)
        if fallback_validated.status == "ok":
            return RepairOutcome(
                status="blocked",
                artifact=fallback_validated.artifact,
                stage="safe_fallback_artifact",
                repair_used=model is not None,
                errors=validated.errors,
                blocker_reason="artifact_repair_failed",
            )
        return RepairOutcome(
            status="failed",
            artifact=None,
            stage="planner_visible_blocker_failed_validation",
            repair_used=model is not None,
            errors=[*validated.errors, *fallback_validated.errors],
            blocker_reason="fallback_artifact_invalid",
        )


def _raw_parse(invalid_output: str) -> dict[str, Any] | None:
    return parse_json_object(invalid_output)


def _deterministic_schema_patch(
    payload: dict[str, Any],
    *,
    expected_type: str,
    context: RepairContext,
) -> dict[str, Any]:
    patched = dict(payload)
    patched["artifact_type"] = expected_type
    patched.setdefault("round", context.round_number)
    if expected_type == "execution_result":
        if context.work_item_id and not patched.get("work_item_id"):
            patched["work_item_id"] = context.work_item_id
        if context.merge_index is not None and not patched.get("merge_index"):
            patched["merge_index"] = context.merge_index
        if context.agent_id and not patched.get("agent_id"):
            patched["agent_id"] = context.agent_id
        patched.setdefault("status", "blocked")
        patched.setdefault("summary", "Executor output was repaired into a blocked artifact.")
        if patched.get("status") in {"blocked", "failed"} and not patched.get("unexpected_issues"):
            patched["unexpected_issues"] = ["artifact_repair_required"]
        if patched.get("status") == "blocked":
            patched.setdefault("needs_planner_decision", True)
            patched.setdefault("blocker_type", "schema_validation_failed")
            patched.setdefault("continue_without_human_possible", False)
    elif expected_type == "test_result":
        if context.work_item_id and not patched.get("work_item_id"):
            patched["work_item_id"] = context.work_item_id
        if context.merge_index is not None and not patched.get("merge_index"):
            patched["merge_index"] = context.merge_index
        if context.tester_agent_id and not patched.get("tester_agent_id"):
            patched["tester_agent_id"] = context.tester_agent_id
        patched.setdefault("status", "blocked")
        patched.setdefault("summary", "Tester output was repaired into a blocked artifact.")
        patched.setdefault("confidence", "low")
        if patched.get("status") in {"fail", "blocked"} and not patched.get("remaining_work"):
            patched["remaining_work"] = ["artifact_repair_required"]
    return patched


def _fallback_artifact(expected_type: str, context: RepairContext) -> dict[str, Any]:
    if expected_type == "execution_result":
        return {
            "artifact_type": "execution_result",
            "round": context.round_number,
            "work_item_id": context.work_item_id,
            "merge_index": context.merge_index,
            "agent_id": context.agent_id,
            "status": "blocked",
            "summary": "Executor output did not match execution_result schema after repair.",
            "unexpected_issues": ["artifact_repair_failed"],
            "needs_planner_decision": True,
            "blocker_type": "schema_validation_failed",
            "planner_question": "Executor output failed schema validation. Should Planner retry, reassign, or ask the user?",
            "continue_without_human_possible": False,
        }
    if expected_type == "test_result":
        return {
            "artifact_type": "test_result",
            "round": context.round_number,
            "work_item_id": context.work_item_id,
            "merge_index": context.merge_index,
            "tester_agent_id": context.tester_agent_id or context.agent_id,
            "status": "blocked",
            "summary": "Tester output did not match test_result schema after repair.",
            "remaining_work": ["artifact_repair_failed"],
            "confidence": "low",
        }
    return {"artifact_type": expected_type}


def _validate(payload: dict[str, Any], *, expected_type: str) -> RepairOutcome:
    try:
        return RepairOutcome(
            status="ok",
            artifact=validate_artifact(payload, expected_type=expected_type),
            stage="validate",
        )
    except (ArtifactValidationError, ValidationError) as exc:
        errors = getattr(exc, "errors", None)
        if callable(errors):
            errors = errors()
        return RepairOutcome(
            status="failed",
            artifact=None,
            stage="validate",
            errors=errors if isinstance(errors, list) else [{"loc": ["artifact"], "msg": str(exc)}],
        )


def _emit(emit: Any | None, event_type: str, message: str, **payload: Any) -> None:
    if emit is not None:
        emit(event_type, message, **{key: value for key, value in payload.items() if value is not None})
