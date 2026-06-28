from __future__ import annotations

from typing import Any

from .schema import (
    AgentStateMessage,
    ArtifactRef,
    BlobRef,
    MemoryRef,
    PlannerState,
    RunControlState,
    SharedRunState,
    StateUpdate,
    ToolResultRef,
    WorkItemState,
)


def apply_state_update(state: SharedRunState, update: StateUpdate) -> SharedRunState:
    if state.run_id != update.run_id:
        raise ValueError("StateUpdate run_id does not match SharedRunState")
    reducers = {
        "control": reduce_control,
        "planner": reduce_planner,
        "work_items": reduce_work_items,
        "messages": reduce_messages,
        "artifacts": reduce_artifacts,
        "tool_results": reduce_tool_results,
        "blobs": reduce_blobs,
        "memory_refs": reduce_memory_refs,
        "final_report": reduce_final_report,
        "debug_refs": reduce_debug_refs,
    }
    return reducers[update.channel](state, update.payload)


def reduce_control(state: SharedRunState, payload: dict[str, Any]) -> SharedRunState:
    control = state.control.model_copy(update={key: value for key, value in payload.items() if key in RunControlState.model_fields})
    return state.model_copy(update={"control": control})


def reduce_planner(state: SharedRunState, payload: dict[str, Any]) -> SharedRunState:
    planner = state.planner.model_copy(update={key: value for key, value in payload.items() if key in PlannerState.model_fields})
    return state.model_copy(update={"planner": planner})


def reduce_work_items(state: SharedRunState, payload: dict[str, Any]) -> SharedRunState:
    items = dict(state.work_items)
    raw_items = payload.get("items")
    if isinstance(raw_items, list):
        for raw_item in raw_items:
            item = WorkItemState.model_validate(raw_item)
            items[item.work_item_id] = item
    else:
        item = WorkItemState.model_validate(payload)
        items[item.work_item_id] = item
    return state.model_copy(update={"work_items": items})


def reduce_messages(state: SharedRunState, payload: dict[str, Any]) -> SharedRunState:
    messages = {message.message_id: message for message in state.messages}
    raw_messages = payload.get("messages") if isinstance(payload.get("messages"), list) else [payload]
    for raw_message in raw_messages:
        message = AgentStateMessage.model_validate(raw_message)
        messages[message.message_id] = message
    return state.model_copy(update={"messages": list(messages.values())})


def reduce_artifacts(state: SharedRunState, payload: dict[str, Any]) -> SharedRunState:
    artifacts = dict(state.artifacts)
    raw_artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), list) else [payload]
    for raw_artifact in raw_artifacts:
        artifact = ArtifactRef.model_validate(raw_artifact)
        artifacts[artifact.artifact_id] = artifact
    return state.model_copy(update={"artifacts": artifacts})


def reduce_tool_results(state: SharedRunState, payload: dict[str, Any]) -> SharedRunState:
    results = dict(state.tool_results)
    raw_results = payload.get("tool_results") if isinstance(payload.get("tool_results"), list) else [payload]
    for raw_result in raw_results:
        result = ToolResultRef.model_validate(raw_result)
        results[result.result_id] = result
    return state.model_copy(update={"tool_results": results})


def reduce_blobs(state: SharedRunState, payload: dict[str, Any]) -> SharedRunState:
    blobs = dict(state.blobs)
    raw_blobs = payload.get("blobs") if isinstance(payload.get("blobs"), list) else [payload]
    for raw_blob in raw_blobs:
        blob = BlobRef.model_validate(raw_blob)
        blobs[blob.blob_id] = blob
    return state.model_copy(update={"blobs": blobs})


def reduce_memory_refs(state: SharedRunState, payload: dict[str, Any]) -> SharedRunState:
    refs = {ref.memory_id: ref for ref in state.memory_refs}
    raw_refs = payload.get("memory_refs") if isinstance(payload.get("memory_refs"), list) else [payload]
    for raw_ref in raw_refs:
        ref = MemoryRef.model_validate(raw_ref)
        refs[ref.memory_id] = ref
    return state.model_copy(update={"memory_refs": list(refs.values())})


def reduce_final_report(state: SharedRunState, payload: dict[str, Any]) -> SharedRunState:
    final_report_ref = str(payload.get("artifact_id") or payload.get("final_report_ref") or "")
    return state.model_copy(update={"final_report_ref": final_report_ref or state.final_report_ref})


def reduce_debug_refs(state: SharedRunState, payload: dict[str, Any]) -> SharedRunState:
    refs = list(state.debug_refs)
    raw_refs = payload.get("debug_refs") if isinstance(payload.get("debug_refs"), list) else [payload.get("debug_ref")]
    refs.extend(str(ref) for ref in raw_refs if ref)
    return state.model_copy(update={"debug_refs": list(dict.fromkeys(refs))})
