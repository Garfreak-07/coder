from __future__ import annotations

from typing import Any

from coder_workbench.actions.schema import ActionResult, ActionSpec


def action_started_payload(spec: ActionSpec, run_context: Any) -> dict[str, object]:
    return {
        "action_id": spec.action_id,
        "action_type": spec.action_type,
        "risk_level": spec.risk_level,
        "requires_permission": spec.requires_permission,
        "run_id": run_context.run_id,
    }


def action_completed_payload(spec: ActionSpec, result: ActionResult) -> dict[str, object]:
    return {
        "action_id": spec.action_id,
        "action_type": spec.action_type,
        "status": result.status,
        "error_code": result.error_code,
        "output_ref": result.output_ref,
        "summary": result.summary,
    }
