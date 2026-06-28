from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from coder_workbench.context.external_refs import preview_text


@dataclass(frozen=True)
class ResultBudget:
    max_inline_chars: int = 12000
    preview_chars: int = 4000


def apply_result_budget(
    payload: dict[str, Any],
    *,
    data: dict[str, Any],
    run_id: str,
    action_id: str,
    action_type: str,
    budget: ResultBudget | None = None,
) -> tuple[dict[str, Any], list[str]]:
    budget = budget or ResultBudget()
    refs: list[str] = []
    compacted = _compact_value(
        payload,
        data=data,
        run_id=run_id,
        action_id=action_id,
        action_type=action_type,
        budget=budget,
        path=[],
        refs=refs,
    )
    if not isinstance(compacted, dict):
        return {"content": compacted}, refs
    return compacted, refs


def _compact_value(
    value: Any,
    *,
    data: dict[str, Any],
    run_id: str,
    action_id: str,
    action_type: str,
    budget: ResultBudget,
    path: list[str],
    refs: list[str],
) -> Any:
    if isinstance(value, str):
        if len(value) <= budget.max_inline_chars:
            return value
        externalized = _store_value(
            value,
            data=data,
            run_id=run_id,
            action_id=action_id,
            action_type=action_type,
            path=path,
            preview_chars=budget.preview_chars,
        )
        refs.append(str(externalized["blob_id"]))
        return externalized
    if isinstance(value, dict):
        return {
            str(key): _compact_value(
                item,
                data=data,
                run_id=run_id,
                action_id=action_id,
                action_type=action_type,
                budget=budget,
                path=[*path, str(key)],
                refs=refs,
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _compact_value(
                item,
                data=data,
                run_id=run_id,
                action_id=action_id,
                action_type=action_type,
                budget=budget,
                path=[*path, str(index)],
                refs=refs,
            )
            for index, item in enumerate(value)
        ]
    return value


def _store_value(
    value: str,
    *,
    data: dict[str, Any],
    run_id: str,
    action_id: str,
    action_type: str,
    path: list[str],
    preview_chars: int,
) -> dict[str, Any]:
    path_key = ".".join(path) or "result"
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    blob_id = f"sha256:{digest}"
    preview = preview_text(value, preview_chars)
    externalized = {
        "blob_id": blob_id,
        "ref_type": "tool-result",
        "field_path": path_key,
        "preview": preview,
        "original_chars": len(value),
        "media_type": "text/plain; charset=utf-8",
    }
    pending = data.setdefault("pending_blob_writes", {})
    if isinstance(pending, dict):
        pending[blob_id] = {**externalized, "content": value}
    replacements = data.setdefault("tool_result_replacements", [])
    if isinstance(replacements, list) and not any(
        isinstance(record, dict)
        and record.get("kind") == "tool-result"
        and record.get("result_id") == f"{action_id}:{path_key}"
        for record in replacements
    ):
        replacements.append(
            {
                "kind": "tool-result",
                "run_id": run_id,
                "round": data.get("active_round") or data.get("round"),
                "work_item_id": data.get("active_work_item_id"),
                "result_id": f"{action_id}:{path_key}",
                "action_id": action_id,
                "action_type": action_type,
                "blob_id": blob_id,
                "replacement": f"<persisted-output blob_id=\"{blob_id}\" field_path=\"{path_key}\">{preview}</persisted-output>",
                "original_chars": len(value),
                "preview_chars": len(preview),
                "priority": _replacement_priority(action_type, data),
            }
        )
    return externalized


def _replacement_priority(action_type: str, data: dict[str, Any]) -> str:
    status = str(data.get("result_status") or data.get("status") or "").lower()
    if "fail" in status or "failed" in action_type:
        return "failed-check"
    if "block" in status:
        return "blocked-check"
    if "command" in action_type or "check" in action_type:
        return "command-output"
    return "verbose-output"


def estimated_chars(value: Any) -> int:
    if isinstance(value, str):
        return len(value)
    try:
        return len(json.dumps(value, ensure_ascii=False, default=str))
    except TypeError:
        return len(str(value))
