from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from coder_workbench.agent_graph.repair import build_repair_prompt, parse_json_object
from coder_workbench.core.artifacts import ArtifactValidationError, validate_artifact


class ArtifactRepairService:
    """Centralized one-shot artifact repair for Planner/Worker/Tester engines."""

    def repair_once(
        self,
        model: Any,
        *,
        expected_type: str,
        invalid_output: str,
        agent_id: str,
        emit: Any | None = None,
        work_item_id: str | None = None,
        merge_index: int | None = None,
        schema_notes: str = "",
    ) -> dict[str, Any] | None:
        _emit(
            emit,
            "agent_graph.agent_call.repair_started",
            "AgentGraph artifact repair started",
            agent_id=agent_id,
            artifact_type=expected_type,
            work_item_id=work_item_id,
            merge_index=merge_index,
        )
        response = model.invoke(
            build_repair_prompt(
                expected_type=expected_type,
                invalid_output=invalid_output,
                errors=[{"loc": ["response"], "msg": "schema validation failed"}],
                schema_notes=schema_notes or f"Return a valid {expected_type} JSON object.",
            )
        )
        payload = parse_json_object(str(getattr(response, "content", response)))
        if payload is None:
            _repair_failed(emit, expected_type, agent_id, work_item_id, merge_index)
            return None
        try:
            repaired = validate_artifact(payload, expected_type=expected_type)
        except (ArtifactValidationError, ValidationError):
            _repair_failed(emit, expected_type, agent_id, work_item_id, merge_index)
            return None
        _emit(
            emit,
            "agent_graph.agent_call.repair_completed",
            "AgentGraph artifact repair completed",
            agent_id=agent_id,
            artifact_type=expected_type,
            work_item_id=work_item_id,
            merge_index=merge_index,
        )
        return repaired


def _repair_failed(
    emit: Any | None,
    expected_type: str,
    agent_id: str,
    work_item_id: str | None,
    merge_index: int | None,
) -> None:
    _emit(
        emit,
        "agent_graph.agent_call.repair_failed",
        "AgentGraph artifact repair failed",
        agent_id=agent_id,
        artifact_type=expected_type,
        work_item_id=work_item_id,
        merge_index=merge_index,
    )


def _emit(emit: Any | None, event_type: str, message: str, **payload: Any) -> None:
    if emit is not None:
        emit(event_type, message, **{key: value for key, value in payload.items() if value is not None})
