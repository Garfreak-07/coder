from __future__ import annotations

from typing import Any


def build_harness_context_packet(
    *,
    mode: str,
    user_goal: str,
    workflow_id: str,
    agent_id: str,
    round_number: int | None = None,
    work_item: Any | None = None,
    task_envelope: Any | None = None,
    state_view: dict[str, Any] | None = None,
    capability_set: dict[str, Any] | None = None,
    selected_knowledge_pack_ids: list[str] | None = None,
    selected_skill_pack_ids: list[str] | None = None,
    selected_memory_pack_ids: list[str] | None = None,
    evidence_refs: list[str] | None = None,
    native_event_refs: list[str] | None = None,
) -> dict[str, Any]:
    packet = {
        "schema_version": "harness-context-packet/v1",
        "mode": mode,
        "workflow_id": workflow_id,
        "agent_id": agent_id,
        "round": round_number,
        "hot": {
            "user_goal": user_goal,
        },
        "warm": {},
        "cold_refs": [],
    }
    if mode == "planning_chat":
        packet["hot"].update(
            {
                "selected_knowledge_pack_ids": list(selected_knowledge_pack_ids or []),
                "selected_skill_pack_ids": list(selected_skill_pack_ids or []),
                "selected_memory_pack_ids": list(selected_memory_pack_ids or []),
            }
        )
        packet["warm"]["workflow_summary"] = {"workflow_id": workflow_id}
    elif mode == "workflow_supervisor":
        packet["hot"]["planner_authority"] = "primary_planner"
        packet["warm"]["run_state_summary"] = _state_summary(state_view or {})
        packet["warm"]["capability_summary"] = _capability_summary(capability_set or {})
        _append_refs(packet, "evidence", evidence_refs or [])
        _append_refs(packet, "native_runtime", native_event_refs or [])
    elif mode == "task_execution":
        packet["hot"]["work_item"] = _model_or_dict(work_item)
        envelope = _model_or_dict(task_envelope)
        packet["hot"]["task_envelope"] = _task_envelope_summary(envelope)
        packet["warm"]["capability_summary"] = _capability_summary(capability_set or {})
        _append_refs(packet, "upstream", list(envelope.get("upstream_refs") or []))
        _append_refs(packet, "planner_order", [str(envelope.get("planner_order_ref"))] if envelope.get("planner_order_ref") else [])
    else:
        packet["warm"]["state_summary"] = _state_summary(state_view or {})
    return {key: value for key, value in packet.items() if value not in (None, {}, [])}


def _model_or_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json")
    return {"value": str(value)}


def _task_envelope_summary(envelope: dict[str, Any]) -> dict[str, Any]:
    keep = {
        "round",
        "work_item_id",
        "merge_index",
        "assigned_agent_id",
        "task_summary",
        "constraints",
        "allowed_skill_ids",
        "loaded_skill_refs",
        "omitted_skill_ids",
        "estimated_skill_tokens",
    }
    return {key: envelope[key] for key in keep if key in envelope}


def _state_summary(state_view: dict[str, Any]) -> dict[str, Any]:
    keep = {
        "status",
        "round",
        "workflow_id",
        "run_id",
        "current_goal",
        "plan_status",
        "completed_count",
        "blocked_count",
    }
    summary = {key: state_view[key] for key in keep if key in state_view}
    work_items = state_view.get("work_items")
    if isinstance(work_items, dict):
        summary["work_items"] = [
            _small_record(record)
            for record in work_items.values()
            if isinstance(record, dict)
        ][:10]
    return summary


def _capability_summary(capability_set: dict[str, Any]) -> dict[str, Any]:
    return {
        "tools": [tool.get("name") for tool in capability_set.get("tools", []) if isinstance(tool, dict)],
        "skills": [skill.get("skill_id") for skill in capability_set.get("skills", []) if isinstance(skill, dict)],
        "denied": [item.get("name") for item in capability_set.get("denied", []) if isinstance(item, dict)],
    }


def _small_record(record: dict[str, Any]) -> dict[str, Any]:
    keep = {"work_item_id", "agent_id", "status", "summary", "execution_result_ref"}
    return {key: record[key] for key in keep if key in record}


def _append_refs(packet: dict[str, Any], ref_type: str, refs: list[str]) -> None:
    clean_refs = [ref for ref in refs if ref]
    if clean_refs:
        packet.setdefault("cold_refs", []).append({"ref_type": ref_type, "refs": clean_refs})


__all__ = ["build_harness_context_packet"]
