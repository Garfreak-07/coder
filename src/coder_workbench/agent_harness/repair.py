from __future__ import annotations

from typing import Any

from coder_workbench.agent_harness.artifact_repair_pipeline import ArtifactRepairPipeline, RepairContext


class ArtifactRepairService:
    """Centralized one-shot artifact repair for Planner/Executor/Tester engines."""

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
        outcome = ArtifactRepairPipeline().repair(
            expected_type=expected_type,
            invalid_output=invalid_output,
            model=model,
            context=RepairContext(
                agent_id=agent_id,
                work_item_id=work_item_id,
                merge_index=merge_index,
                schema_notes=schema_notes,
                emit=emit,
            ),
        )
        return outcome.artifact
