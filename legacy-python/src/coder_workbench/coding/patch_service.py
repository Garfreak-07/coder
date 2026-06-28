from __future__ import annotations

from pathlib import Path
from typing import Any

from coder_workbench.coding.risk_map import build_risk_map, is_risk_path
from coder_workbench.tools.patching import apply_patch, propose_patch, rollback_patch


class PatchService:
    def __init__(self, repo_root: str | Path, *, scopes: list[str] | None = None, data: dict[str, Any] | None = None) -> None:
        self.repo_root = str(Path(repo_root).resolve())
        self.scopes = scopes or []
        self.data = data or {}

    def preview(self, proposed_changes: Any, *, risk_map: dict[str, Any] | None = None) -> dict[str, Any]:
        changes = _normalize_changes(proposed_changes)
        active_risk_map = risk_map or build_risk_map(self.repo_root).model_dump(mode="json")
        risky_changes = [
            change
            for change in changes
            if is_risk_path(str(change.get("path") or change.get("file") or ""), active_risk_map)
        ]
        if risky_changes:
            return {
                "status": "blocked",
                "error_code": "risk_path",
                "message": "Proposed change targets a risk path.",
                "risk_errors": [
                    {
                        "path": str(change.get("path") or change.get("file") or ""),
                        "code": "risk_path",
                        "message": "Risk paths require Planner intervention before preview or apply.",
                    }
                    for change in risky_changes
                ],
                "risky_changes": risky_changes,
            }
        return propose_patch({"changes": changes}, self._runtime_context())

    def apply(self, patch: dict[str, Any], *, approved: bool = False) -> dict[str, Any]:
        return apply_patch({"patch": patch, "approved": approved}, self._runtime_context())

    def rollback(self, snapshot_id: str) -> dict[str, Any]:
        return rollback_patch({"snapshot_id": snapshot_id}, self._runtime_context())

    def _runtime_context(self) -> dict[str, Any]:
        return {"repo_root": self.repo_root, "scopes": self.scopes, "data": self.data}


def _normalize_changes(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        for key in ("changes", "files", "patches"):
            if isinstance(value.get(key), list):
                return [dict(item) for item in value[key] if isinstance(item, dict)]
        if "path" in value:
            return [dict(value)]
        return []
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict)]
    return []
