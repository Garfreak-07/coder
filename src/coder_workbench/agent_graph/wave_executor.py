from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from time import monotonic
from typing import Any, Callable

from coder_workbench.agent_graph.artifacts import graph_artifact_id
from coder_workbench.agent_graph.schema import ExecutionRecord, WorkItemOutcome


BuildOutcome = Callable[[dict[str, Any]], WorkItemOutcome]


@dataclass(frozen=True)
class WorkItemRuntimePolicy:
    timeout_seconds: float = 600
    max_retries: int = 0
    retry_on_status_codes: list[str] = field(default_factory=list)
    allow_partial_result: bool = True


@dataclass(frozen=True)
class WorkItemAttempt:
    attempt: int
    status: str
    started_at: str
    completed_at: str | None
    elapsed_ms: int | None
    error_code: str | None
    artifact_ref: str | None


class PartialWorkItemError(RuntimeError):
    def __init__(self, message: str, *, partial_outcome: WorkItemOutcome | None = None, error_code: str = "partial_result") -> None:
        self.partial_outcome = partial_outcome
        self.error_code = error_code
        super().__init__(message)


class WaveExecutor:
    def __init__(
        self,
        build_work_item_outcome: BuildOutcome,
        *,
        runtime_policy: WorkItemRuntimePolicy | None = None,
        emit: Any | None = None,
        run_control: Any | None = None,
        enable_retry: bool | None = None,
    ) -> None:
        self.build_work_item_outcome = build_work_item_outcome
        self.runtime_policy = runtime_policy or WorkItemRuntimePolicy()
        self.emit = emit
        self.run_control = run_control
        self.enable_retry = _feature_enabled("CODER_ENABLE_WAVE_RETRY") if enable_retry is None else bool(enable_retry)
        self.last_diagnostics: dict[str, Any] = {}

    def run_wave(self, wave: Any, task_contexts: list[dict[str, Any]]) -> list[WorkItemOutcome]:
        outcomes: list[WorkItemOutcome] = []
        if not wave.items:
            return outcomes
        diagnostics = {
            "wave_index": getattr(wave, "wave_index", None),
            "attempts": {},
            "completed": 0,
            "failed": 0,
            "blocked": 0,
            "cancelled": 0,
            "timed_out": 0,
        }
        with ThreadPoolExecutor(max_workers=max(1, len(wave.items))) as pool:
            futures = {
                pool.submit(self._run_attempts, context): context
                for context in task_contexts
            }
            for future, context in futures.items():
                item = context["item"]
                try:
                    outcome, attempts = future.result(timeout=max(0.001, float(self.runtime_policy.timeout_seconds)))
                except TimeoutError:
                    future.cancel()
                    outcome = _blocked_outcome(item, f"Work item timed out after {self.runtime_policy.timeout_seconds} seconds.", "work_item_timeout")
                    attempts = [
                        WorkItemAttempt(
                            attempt=1,
                            status="timeout",
                            started_at=_now_iso(),
                            completed_at=_now_iso(),
                            elapsed_ms=None,
                            error_code="work_item_timeout",
                            artifact_ref=outcome.execution.execution_result_ref,
                        )
                    ]
                    diagnostics["timed_out"] += 1
                    _emit(self.emit, "agent_task.timeout", outcome.execution.execution_summary, work_item_id=item.work_item_id)
                except Exception as exc:
                    partial = getattr(exc, "partial_outcome", None)
                    error_code = str(getattr(exc, "error_code", "work_item_exception"))
                    if self.runtime_policy.allow_partial_result and isinstance(partial, WorkItemOutcome):
                        outcome = partial
                    else:
                        outcome = _failed_outcome(item, f"Work item failed: {exc}", error_code)
                    attempts = [
                        WorkItemAttempt(
                            attempt=1,
                            status=outcome.execution.status,
                            started_at=_now_iso(),
                            completed_at=_now_iso(),
                            elapsed_ms=None,
                            error_code=error_code,
                            artifact_ref=outcome.execution.execution_result_ref,
                        )
                    ]
                    _emit(self.emit, "agent_task.attempt.failed", outcome.execution.execution_summary, work_item_id=item.work_item_id)
                outcomes.append(outcome)
                diagnostics["attempts"][item.work_item_id] = [asdict(attempt) for attempt in attempts]
                if _is_cancelled(outcome):
                    diagnostics["cancelled"] += 1
                elif outcome.execution.status == "completed":
                    diagnostics["completed"] += 1
                elif outcome.execution.status == "blocked":
                    diagnostics["blocked"] += 1
                else:
                    diagnostics["failed"] += 1
        self.last_diagnostics = diagnostics
        _emit(self.emit, "agent_graph.wave.diagnostics", "Wave diagnostics recorded", diagnostics=diagnostics)
        return outcomes

    def _run_attempts(self, context: dict[str, Any]) -> tuple[WorkItemOutcome, list[WorkItemAttempt]]:
        item = context["item"]
        attempts: list[WorkItemAttempt] = []
        max_attempts = 1 + (self.runtime_policy.max_retries if self.enable_retry else 0)
        for attempt_number in range(1, max_attempts + 1):
            if _cancel_requested(self.run_control):
                outcome = _blocked_outcome(item, "Work item cancelled before execution.", "work_item_cancelled")
                attempts.append(
                    WorkItemAttempt(
                        attempt=attempt_number,
                        status="cancelled",
                        started_at=_now_iso(),
                        completed_at=_now_iso(),
                        elapsed_ms=0,
                        error_code="work_item_cancelled",
                        artifact_ref=outcome.execution.execution_result_ref,
                    )
                )
                _emit(self.emit, "agent_task.cancelled", "Work item cancelled before execution", work_item_id=item.work_item_id)
                return outcome, attempts

            started = monotonic()
            started_at = _now_iso()
            _emit(
                self.emit,
                "agent_task.attempt.started",
                f"Work item attempt {attempt_number} started",
                work_item_id=item.work_item_id,
                attempt=attempt_number,
            )
            try:
                outcome = self.build_work_item_outcome(context)
            except PartialWorkItemError as exc:
                if self.runtime_policy.allow_partial_result and exc.partial_outcome is not None:
                    outcome = exc.partial_outcome
                else:
                    outcome = _failed_outcome(item, f"Work item failed: {exc}", exc.error_code)
            except Exception as exc:
                outcome = _failed_outcome(item, f"Work item failed: {exc}", "work_item_exception")

            error_code = _outcome_error_code(outcome)
            attempts.append(
                WorkItemAttempt(
                    attempt=attempt_number,
                    status=outcome.execution.status,
                    started_at=started_at,
                    completed_at=_now_iso(),
                    elapsed_ms=int((monotonic() - started) * 1000),
                    error_code=error_code,
                    artifact_ref=outcome.execution.execution_result_ref,
                )
            )
            if outcome.execution.status == "completed":
                _emit(
                    self.emit,
                    "agent_task.attempt.completed",
                    f"Work item attempt {attempt_number} completed",
                    work_item_id=item.work_item_id,
                    attempt=attempt_number,
                )
                return outcome, attempts
            _emit(
                self.emit,
                "agent_task.attempt.failed",
                f"Work item attempt {attempt_number} did not complete",
                work_item_id=item.work_item_id,
                attempt=attempt_number,
                status=outcome.execution.status,
                error_code=error_code,
            )
            if attempt_number < max_attempts and error_code in set(self.runtime_policy.retry_on_status_codes):
                _emit(
                    self.emit,
                    "agent_task.retry.scheduled",
                    f"Retry scheduled for work item {item.work_item_id}",
                    work_item_id=item.work_item_id,
                    attempt=attempt_number + 1,
                    error_code=error_code,
                )
                continue
            return outcome, attempts
        return _failed_outcome(item, "Work item failed after retries.", "work_item_retries_exhausted"), attempts


def _failed_outcome(item: Any, summary: str, error_code: str) -> WorkItemOutcome:
    return WorkItemOutcome(
        work_item_id=item.work_item_id,
        merge_index=item.merge_index,
        execution=ExecutionRecord(
            work_item_id=item.work_item_id,
            merge_index=item.merge_index,
            agent_id=item.assignee_agent_id,
            status="failed",
            execution_summary=summary,
            execution_result_ref=graph_artifact_id("execution_result", item.work_item_id),
            artifact_payload={
                "artifact_type": "execution_result",
                "round": 1,
                "work_item_id": item.work_item_id,
                "merge_index": item.merge_index,
                "agent_id": item.assignee_agent_id,
                "status": "failed",
                "summary": summary,
                "unexpected_issues": [error_code],
            },
        ),
        tests=[],
    )


def _blocked_outcome(item: Any, summary: str, error_code: str) -> WorkItemOutcome:
    return WorkItemOutcome(
        work_item_id=item.work_item_id,
        merge_index=item.merge_index,
        execution=ExecutionRecord(
            work_item_id=item.work_item_id,
            merge_index=item.merge_index,
            agent_id=item.assignee_agent_id,
            status="blocked",
            execution_summary=summary,
            execution_result_ref=graph_artifact_id("execution_result", item.work_item_id),
            artifact_payload={
                "artifact_type": "execution_result",
                "round": 1,
                "work_item_id": item.work_item_id,
                "merge_index": item.merge_index,
                "agent_id": item.assignee_agent_id,
                "status": "blocked",
                "summary": summary,
                "unexpected_issues": [error_code],
                "needs_planner_decision": True,
                "blocker_type": "technical_blocker",
                "continue_without_human_possible": True,
            },
        ),
        tests=[],
    )


def _outcome_error_code(outcome: WorkItemOutcome) -> str | None:
    payload = outcome.execution.artifact_payload or {}
    if isinstance(payload.get("error_code"), str):
        return payload["error_code"]
    issues = payload.get("unexpected_issues")
    if isinstance(issues, list) and issues:
        return str(issues[0])
    if isinstance(payload.get("blocker_type"), str):
        return payload["blocker_type"]
    return outcome.execution.status if outcome.execution.status != "completed" else None


def _cancel_requested(run_control: Any | None) -> bool:
    return bool(getattr(run_control, "cancel_requested", False) or getattr(run_control, "cancel_requested_event", False))


def _is_cancelled(outcome: WorkItemOutcome) -> bool:
    payload = outcome.execution.artifact_payload or {}
    issues = payload.get("unexpected_issues")
    return outcome.execution.status == "blocked" and isinstance(issues, list) and "work_item_cancelled" in issues


def _emit(emit: Any | None, event_type: str, message: str, **payload: Any) -> None:
    if emit is not None:
        emit(event_type, message, **{key: value for key, value in payload.items() if value is not None})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _feature_enabled(name: str) -> bool:
    return str(os.getenv(name) or "").strip().lower() in {"1", "true", "yes", "on"}
