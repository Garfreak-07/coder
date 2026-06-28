from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from coder_workbench.agent_harness.action_protocol import HarnessActionRequest, HarnessObservation
from coder_workbench.agent_harness.session import CodeWorkerLoopState


PATCH_ACTION_TYPES = {"propose_patch", "apply_patch_sandbox"}


class PatchWorkflowDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed: bool
    reason: str = ""
    error_code: str | None = None
    observation: HarnessObservation | None = None


class PatchWorkflow:
    def before_action(self, request: HarnessActionRequest, state: CodeWorkerLoopState) -> PatchWorkflowDecision:
        if request.action_type not in PATCH_ACTION_TYPES:
            return PatchWorkflowDecision(allowed=True)
        if _latest_patch_failure_requires_reread(state):
            reason = "Patch failed previously; reread or search affected files before another patch attempt."
            return PatchWorkflowDecision(
                allowed=False,
                reason=reason,
                error_code="patch_requires_reread",
                observation=HarnessObservation(
                    action_id=f"{request.action_id}-patch-workflow",
                    action_type="patch_workflow",
                    status="blocked",
                    summary=reason,
                    evidence_refs=[f"harness_observation:{request.action_id}-patch-workflow"],
                    error_code="patch_requires_reread",
                ),
            )
        return PatchWorkflowDecision(allowed=True)

    def should_auto_inspect(self, request: HarnessActionRequest, observation: HarnessObservation) -> bool:
        return request.action_type == "apply_patch_sandbox" and observation.status == "ok"

    def auto_inspect_request(self, request: HarnessActionRequest) -> HarnessActionRequest:
        paths = _patch_paths(request.payload)
        payload: dict[str, Any] = {"paths": paths} if paths else {}
        return HarnessActionRequest(
            action_id=f"{request.action_id}-inspect-diff",
            action_type="inspect_git_diff",
            payload=payload,
            reason="Runtime auto-inspects git diff after a sandbox patch.",
            risk_level="low",
            expected_evidence=["git diff summary"],
        )


def _latest_patch_failure_requires_reread(state: CodeWorkerLoopState) -> bool:
    for observation in reversed(state.session.observations):
        if observation.action_type in {"read_file", "search_files"} and observation.status == "ok":
            return False
        if observation.action_type in PATCH_ACTION_TYPES:
            return observation.status != "ok"
    return False


def _patch_paths(payload: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for item in _patch_items(payload):
        path = str(item.get("path") or item.get("file") or "").strip()
        if path:
            paths.append(path)
    return _unique(paths)


def _patch_items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        for key in ("changes", "proposed_changes", "files", "patches"):
            if isinstance(value.get(key), list):
                return [dict(item) for item in value[key] if isinstance(item, dict)]
        patch = value.get("patch")
        if isinstance(patch, dict):
            return _patch_items(patch)
        if "path" in value or "file" in value:
            return [dict(value)]
        return []
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict)]
    return []


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output
