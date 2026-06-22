from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from coder_workbench.context.budget import ContextBudget
from coder_workbench.context.external_refs import ContextExternalRefStore
from coder_workbench.skills import estimate_tokens


PRESERVED_KEYS = {
    "artifact_id",
    "artifact_type",
    "work_item_id",
    "round",
    "round_number",
    "merge_index",
    "status",
    "execution_status",
    "verification_status",
    "failure_reason",
    "blocker_reason",
    "reason",
    "evidence",
    "evidence_refs",
    "patch_refs",
    "planner_order_ref",
    "execution_result_ref",
}


@dataclass(frozen=True)
class CompactionResult:
    packet: dict[str, Any]
    token_estimate_before: int
    token_estimate_after: int
    externalized_refs: list[str] = field(default_factory=list)
    summaries: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class ContextCompactor:
    def __init__(self, budget: ContextBudget | None = None) -> None:
        self.budget = budget or ContextBudget()

    def compact(
        self,
        packet: dict[str, Any],
        *,
        run_id: str,
        work_item_id: str,
        store: ContextExternalRefStore,
    ) -> CompactionResult:
        before = token_estimate(packet)
        if before <= self.budget.max_input_tokens:
            return CompactionResult(
                packet=dict(packet),
                token_estimate_before=before,
                token_estimate_after=before,
            )

        externalized: list[str] = []
        summaries: list[dict[str, Any]] = []
        warnings: list[str] = []
        compacted = self._compact_value(
            packet,
            run_id=run_id,
            work_item_id=work_item_id,
            store=store,
            path=[],
            externalized=externalized,
            summaries=summaries,
        )
        after = token_estimate(compacted)
        if after > self.budget.max_input_tokens:
            warnings.append(
                f"Context packet is still estimated at {after} tokens after compaction "
                f"against budget {self.budget.max_input_tokens}."
            )
        if not isinstance(compacted, dict):
            compacted = {"packet_preview": compacted}
        return CompactionResult(
            packet=compacted,
            token_estimate_before=before,
            token_estimate_after=after,
            externalized_refs=externalized,
            summaries=summaries,
            warnings=warnings,
        )

    def _compact_value(
        self,
        value: Any,
        *,
        run_id: str,
        work_item_id: str,
        store: ContextExternalRefStore,
        path: list[str],
        externalized: list[str],
        summaries: list[dict[str, Any]],
    ) -> Any:
        if isinstance(value, str):
            key = path[-1] if path else ""
            if key in PRESERVED_KEYS:
                return value
            threshold = self._string_threshold_for_path(path)
            if estimate_tokens(value) <= threshold:
                return value
            ref = store.write(
                run_id=run_id,
                work_item_id=work_item_id,
                path=path,
                value=value,
                preview_chars=max(200, min(1200, threshold * 2)),
            )
            externalized.append(ref.ref)
            summaries.append(
                {
                    "field_path": ref.path,
                    "full_ref": ref.ref,
                    "original_chars": ref.original_chars,
                    "preview": ref.preview,
                }
            )
            return {
                "content_preview": ref.preview,
                "truncated": True,
                "full_ref": ref.ref,
                "original_chars": ref.original_chars,
            }
        if isinstance(value, list):
            return [
                self._compact_value(
                    item,
                    run_id=run_id,
                    work_item_id=work_item_id,
                    store=store,
                    path=[*path, str(index)],
                    externalized=externalized,
                    summaries=summaries,
                )
                for index, item in enumerate(value)
            ]
        if isinstance(value, dict):
            return {
                key: self._compact_value(
                    item,
                    run_id=run_id,
                    work_item_id=work_item_id,
                    store=store,
                    path=[*path, str(key)],
                    externalized=externalized,
                    summaries=summaries,
                )
                for key, item in value.items()
            }
        return value

    def _string_threshold_for_path(self, path: list[str]) -> int:
        keys = set(path)
        if {"output", "command_output", "check_output"} & keys:
            return max(1, self.budget.max_tool_result_tokens)
        if {"content", "included_artifacts", "artifact_payload", "patch", "diff"} & keys:
            return max(1, self.budget.max_artifact_tokens)
        return max(1, min(self.budget.max_artifact_tokens, self.budget.max_tool_result_tokens))


def token_estimate(value: Any) -> int:
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except TypeError:
        text = str(value)
    return estimate_tokens(text)
