from __future__ import annotations

from typing import Any

from .schema import SharedRunState


def build_planner_state_view(state: SharedRunState) -> dict[str, Any]:
    return {
        "user_request": state.user_request,
        "round": state.control.round,
        "planner": state.planner.model_dump(mode="json"),
        "execution_results": [
            item.model_dump(mode="json")
            for item in state.work_items.values()
            if item.execution_result_ref
        ],
        "blocked_facts": [
            {
                "work_item_id": item.work_item_id,
                "blocked_reason": item.blocked_reason,
                "execution_result_ref": item.execution_result_ref,
            }
            for item in state.work_items.values()
            if item.status == "blocked"
        ],
        "memory_refs": [ref.model_dump(mode="json") for ref in state.memory_refs],
    }


def build_executor_state_view(state: SharedRunState, work_item_id: str) -> dict[str, Any]:
    item = state.work_items.get(work_item_id)
    return {
        "assigned_work_item": item.model_dump(mode="json") if item else None,
        "planner_order_ref": state.planner.planner_order_ref,
        "upstream_refs": [
            message.model_dump(mode="json")
            for message in state.messages
            if work_item_id in message.summary or work_item_id in message.artifact_refs
        ],
        "memory_refs": [ref.model_dump(mode="json") for ref in state.memory_refs if ref.scope == "project"],
    }


def build_final_report_state_view(state: SharedRunState) -> dict[str, Any]:
    return {
        "run_status": state.control.status,
        "planner_decision_ref": state.planner.planner_decision_ref,
        "round_summary_ref": state.planner.round_summary_ref,
        "work_items": [item.model_dump(mode="json") for item in state.work_items.values()],
        "artifact_refs": [ref.model_dump(mode="json") for ref in state.artifacts.values()],
        "memory_refs": [ref.model_dump(mode="json") for ref in state.memory_refs],
        "final_report_ref": state.final_report_ref,
    }


def build_debug_state_view(state: SharedRunState) -> dict[str, Any]:
    return {
        "refs": {
            "artifacts": sorted(state.artifacts),
            "tool_results": sorted(state.tool_results),
            "blobs": sorted(state.blobs),
            "debug_refs": state.debug_refs,
        }
    }
