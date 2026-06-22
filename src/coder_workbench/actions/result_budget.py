from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


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
        ref = _store_value(
            value,
            data=data,
            run_id=run_id,
            action_id=action_id,
            action_type=action_type,
            path=path,
        )
        refs.append(ref)
        return {
            "content_preview": _preview(value, budget.preview_chars),
            "truncated": True,
            "full_result_ref": ref,
            "original_chars": len(value),
        }
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
) -> str:
    path_key = ".".join(path) or "result"
    digest = hashlib.sha256(f"{action_id}\0{path_key}\0{value}".encode("utf-8")).hexdigest()[:16]
    ref = f"tool_result:{run_id}:{action_id}:{digest}"
    store = data.setdefault("tool_result_store", {})
    if isinstance(store, dict):
        store[ref] = {
            "action_id": action_id,
            "action_type": action_type,
            "field_path": path_key,
            "content": value,
            "original_chars": len(value),
        }
    return ref


def _preview(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    head = max(1, limit // 2)
    tail = max(1, limit - head)
    return f"{value[:head]}\n...<truncated>...\n{value[-tail:]}"


def estimated_chars(value: Any) -> int:
    if isinstance(value, str):
        return len(value)
    try:
        return len(json.dumps(value, ensure_ascii=False, default=str))
    except TypeError:
        return len(str(value))
