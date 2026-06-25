from __future__ import annotations

from typing import Any, Callable

from .profiles import INTERNAL_FALLBACK_PROVIDER_ID
from .runtime_context import HarnessRunRequest, HarnessRunResult


class InternalFallbackProvider:
    """Compatibility provider used while AgentRun is migrated incrementally."""

    provider_id = INTERNAL_FALLBACK_PROVIDER_ID

    def __init__(
        self,
        *,
        planner_order_runner: Callable[..., Any] | None = None,
        task_execution_runner: Callable[..., Any] | None = None,
        planner_decision_runner: Callable[..., Any] | None = None,
        planning_chat_runner: Callable[..., Any] | None = None,
    ) -> None:
        self.planner_order_runner = planner_order_runner
        self.task_execution_runner = task_execution_runner
        self.planner_decision_runner = planner_decision_runner
        self.planning_chat_runner = planning_chat_runner

    def is_available(self) -> bool:
        return True

    def run(self, request: HarnessRunRequest, *, emit: Any | None = None) -> HarnessRunResult:
        operation = str(request.input_artifacts.get("legacy_operation") or "")
        runner = self._runner_for_operation(operation)
        if runner is not None:
            if emit is not None:
                emit(
                    "harness_runtime.fallback.legacy",
                    "InternalFallbackProvider routed request to legacy runtime",
                    mode=request.mode,
                    profile_id=request.profile.id,
                    legacy_operation=operation,
                )
            output = runner(emit=emit, **dict(request.input_artifacts.get("legacy_kwargs") or {}))
            result = HarnessRunResult(
                status="completed",
                artifact_type=_artifact_type_for_operation(operation, output),
                artifact=_artifact_payload(output),
            )
            object.__setattr__(result, "_legacy_output", output)
            return result

        if emit is not None:
            emit(
                "harness_runtime.fallback.unconfigured",
                "InternalFallbackProvider was invoked without a legacy runtime adapter",
                mode=request.mode,
                profile_id=request.profile.id,
            )
        return HarnessRunResult(
            status="failed",
            error={
                "code": "fallback_provider_unconfigured",
                "message": "InternalFallbackProvider is not wired to a legacy runtime adapter for this request.",
            },
        )

    def _runner_for_operation(self, operation: str) -> Callable[..., Any] | None:
        return {
            "planning_chat": self.planning_chat_runner,
            "planner_order": self.planner_order_runner,
            "task_execution": self.task_execution_runner,
            "planner_decision": self.planner_decision_runner,
        }.get(operation)


def _artifact_type_for_operation(operation: str, output: Any) -> str | None:
    payload = _artifact_payload(output)
    if payload is not None and payload.get("artifact_type"):
        return str(payload["artifact_type"])
    return {
        "planning_chat": "project_plan_draft",
        "planner_order": "planner_order",
        "task_execution": "execution_result",
        "planner_decision": "planner_decision",
    }.get(operation)


def _artifact_payload(output: Any) -> dict[str, Any] | None:
    if isinstance(output, dict):
        return dict(output)
    artifact_payload = getattr(output, "artifact_payload", None)
    if isinstance(artifact_payload, dict):
        return dict(artifact_payload)
    model_dump = getattr(output, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json")
    return None


__all__ = ["InternalFallbackProvider"]
