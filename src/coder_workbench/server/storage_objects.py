from __future__ import annotations

from typing import Any, Callable

from coder_workbench.runtime import RunEvent


WriteBlob = Callable[[str], str]
ValidateBlobId = Callable[[str], None]


def externalize_large_values(value: Any, *, write_blob: WriteBlob, threshold: int) -> Any:
    if isinstance(value, str):
        if len(value) >= threshold:
            blob_id = write_blob(value)
            return {
                "blob_id": blob_id,
                "size_chars": len(value),
                "media_type": "text/plain; charset=utf-8",
            }
        return value
    if isinstance(value, list):
        return [externalize_large_values(item, write_blob=write_blob, threshold=threshold) for item in value]
    if isinstance(value, dict):
        return {
            key: externalize_large_values(item, write_blob=write_blob, threshold=threshold)
            for key, item in value.items()
        }
    return value


def collect_blob_ids(value: Any, blob_ids: set[str], *, validate_blob_id: ValidateBlobId) -> None:
    if isinstance(value, dict):
        blob_id = value.get("blob_id")
        if isinstance(blob_id, str):
            try:
                validate_blob_id(blob_id)
            except KeyError:
                pass
            else:
                blob_ids.add(blob_id)
        for item in value.values():
            collect_blob_ids(item, blob_ids, validate_blob_id=validate_blob_id)
    elif isinstance(value, list):
        for item in value:
            collect_blob_ids(item, blob_ids, validate_blob_id=validate_blob_id)


def embedded_context_packet(event: RunEvent, packet_id: str) -> dict[str, Any] | None:
    if event.type != "agent.context_packet":
        return None
    if str(event.payload.get("packet_id") or event.id) != packet_id:
        return None
    packet = event.payload.get("packet")
    return packet if isinstance(packet, dict) else None


def embedded_tool_result(event: RunEvent, tool_result_id: str) -> dict[str, Any] | None:
    if event.type != "tool.result":
        return None
    if str(event.payload.get("tool_result_id") or event.id) != tool_result_id:
        return None
    result = event.payload.get("result")
    return result if isinstance(result, dict) else None


def context_packet_summary(packet: Any) -> dict[str, Any]:
    if not isinstance(packet, dict):
        return {"type": type(packet).__name__}

    agent = packet.get("agent") if isinstance(packet.get("agent"), dict) else {}
    token_estimate = packet.get("token_estimate") if isinstance(packet.get("token_estimate"), dict) else {}
    loop = packet.get("loop") if isinstance(packet.get("loop"), dict) else {}
    selected_state_keys = packet.get("selected_state_keys")
    state_summaries = packet.get("state_summaries")
    allowed_tools = packet.get("allowed_tools")

    summary = {
        "agent_id": agent.get("id"),
        "agent_name": agent.get("name"),
        "node_id": packet.get("node_id"),
        "selected_state_keys": selected_state_keys if isinstance(selected_state_keys, list) else [],
        "state_summary_keys": sorted(state_summaries.keys()) if isinstance(state_summaries, dict) else [],
        "tool_count": len(allowed_tools) if isinstance(allowed_tools, list) else 0,
        "estimated_tokens": token_estimate.get("packet"),
        "budget": token_estimate.get("budget"),
        "loop_node_id": loop.get("node_id"),
        "loop_iteration": loop.get("iteration"),
    }
    return {key: value for key, value in summary.items() if value is not None}
