from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import monotonic
from typing import Any, Callable, Literal


ToolStatus = Literal["ok", "blocked", "failed", "cancelled", "timeout"]
ToolHandler = Callable[["ToolExecutionSpec", Any], Any]


@dataclass(frozen=True)
class ToolExecutionSpec:
    action_id: str
    action_type: str
    input: dict[str, Any]
    agent_id: str | None = None
    work_item_id: str | None = None
    timeout_seconds: int = 120
    concurrency_key: str | None = None
    requires_exclusive_access: bool = False
    is_read_only: bool = False
    can_cancel: bool = True
    cancel_pending_on_failure: bool = False
    depends_on: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ToolExecutionResult:
    action_id: str
    action_type: str
    status: ToolStatus
    summary: str
    payload: dict[str, Any]
    error_code: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    elapsed_ms: int | None = None

    def with_timing(
        self,
        *,
        started_at: str,
        completed_at: str,
        elapsed_ms: int,
    ) -> "ToolExecutionResult":
        return ToolExecutionResult(
            action_id=self.action_id,
            action_type=self.action_type,
            status=self.status,
            summary=self.summary,
            payload=self.payload,
            error_code=self.error_code,
            started_at=started_at,
            completed_at=completed_at,
            elapsed_ms=elapsed_ms,
        )


class ToolExecutionService:
    """Conservative internal execution layer for ActionGateway tools.

    The service groups consecutive read-only/non-exclusive tools so they can run
    concurrently, while preserving result order and running all exclusive tools
    alone. It does not own permissions or effects; callers provide the handler
    that ultimately goes through the existing gateway boundary.
    """

    def __init__(self, handlers: dict[str, ToolHandler] | None = None) -> None:
        self.handlers = dict(handlers or {})

    def run_one(
        self,
        spec: ToolExecutionSpec,
        context: Any,
        handler: ToolHandler | None = None,
    ) -> ToolExecutionResult:
        selected = handler or self.handlers.get(spec.action_type)
        if selected is None:
            return ToolExecutionResult(
                action_id=spec.action_id,
                action_type=spec.action_type,
                status="failed",
                summary=f"No tool handler registered for {spec.action_type}.",
                payload={},
                error_code="tool_handler_missing",
            )
        return self._run_one_with_timeout(spec, context, selected)

    def run_batch(
        self,
        specs: list[ToolExecutionSpec],
        context: Any,
        handler: ToolHandler | None = None,
    ) -> list[ToolExecutionResult]:
        results: list[ToolExecutionResult | None] = [None] * len(specs)
        index = 0
        cancel_remaining = False
        while index < len(specs):
            if cancel_remaining:
                spec = specs[index]
                results[index] = self._cancelled_result(spec, reason="Cancelled after earlier hard failure.")
                index += 1
                continue

            spec = specs[index]
            if spec.requires_exclusive_access or not spec.is_read_only:
                result = self.run_one(spec, context, handler)
                results[index] = result
                cancel_remaining = _should_cancel_pending(spec, result)
                index += 1
                continue

            group_start = index
            group: list[ToolExecutionSpec] = []
            while index < len(specs):
                candidate = specs[index]
                if candidate.requires_exclusive_access or not candidate.is_read_only:
                    break
                group.append(candidate)
                index += 1
            group_results = self._run_parallel_group(group, context, handler)
            for offset, result in enumerate(group_results):
                results[group_start + offset] = result
                if _should_cancel_pending(group[offset], result):
                    cancel_remaining = True

        return [result for result in results if result is not None]

    def _run_parallel_group(
        self,
        specs: list[ToolExecutionSpec],
        context: Any,
        handler: ToolHandler | None,
    ) -> list[ToolExecutionResult]:
        if not specs:
            return []
        results: list[ToolExecutionResult | None] = [None] * len(specs)
        with ThreadPoolExecutor(max_workers=max(1, len(specs))) as pool:
            futures: dict[Future[ToolExecutionResult], int] = {
                pool.submit(self.run_one, spec, context, handler): index
                for index, spec in enumerate(specs)
            }
            for future in as_completed(futures):
                results[futures[future]] = future.result()
        return [result for result in results if result is not None]

    def _run_one_with_timeout(
        self,
        spec: ToolExecutionSpec,
        context: Any,
        handler: ToolHandler,
    ) -> ToolExecutionResult:
        started_at = _now_iso()
        started = monotonic()
        _emit(context, "action.execution.started", "Action execution started", spec=spec)
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(handler, spec, context)
        try:
            raw_result = future.result(timeout=max(0.001, float(spec.timeout_seconds)))
        except TimeoutError:
            future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)
            result = ToolExecutionResult(
                action_id=spec.action_id,
                action_type=spec.action_type,
                status="timeout",
                summary=f"Action timed out after {spec.timeout_seconds} seconds.",
                payload={},
                error_code="action_timeout",
                started_at=started_at,
                completed_at=_now_iso(),
                elapsed_ms=_elapsed_ms(started),
            )
            _emit(context, "action.execution.timeout", result.summary, spec=spec, result=result)
            return result
        except Exception as exc:
            executor.shutdown(wait=False, cancel_futures=True)
            result = ToolExecutionResult(
                action_id=spec.action_id,
                action_type=spec.action_type,
                status="failed",
                summary=str(exc),
                payload={},
                error_code="tool_execution_exception",
                started_at=started_at,
                completed_at=_now_iso(),
                elapsed_ms=_elapsed_ms(started),
            )
            _emit(context, "action.execution.failed", result.summary, spec=spec, result=result)
            return result

        executor.shutdown(wait=False, cancel_futures=True)
        result = _coerce_result(raw_result, spec).with_timing(
            started_at=started_at,
            completed_at=_now_iso(),
            elapsed_ms=_elapsed_ms(started),
        )
        event_type = {
            "ok": "action.execution.completed",
            "blocked": "action.execution.blocked",
            "failed": "action.execution.failed",
            "cancelled": "action.execution.cancelled",
            "timeout": "action.execution.timeout",
        }[result.status]
        _emit(context, event_type, result.summary, spec=spec, result=result)
        return result

    def _cancelled_result(self, spec: ToolExecutionSpec, *, reason: str) -> ToolExecutionResult:
        return ToolExecutionResult(
            action_id=spec.action_id,
            action_type=spec.action_type,
            status="cancelled",
            summary=reason,
            payload={},
            error_code="cancelled_by_prior_failure",
            started_at=None,
            completed_at=_now_iso(),
            elapsed_ms=0,
        )


def _coerce_result(raw_result: Any, spec: ToolExecutionSpec) -> ToolExecutionResult:
    if isinstance(raw_result, ToolExecutionResult):
        return raw_result
    status = str(getattr(raw_result, "status", "") or "ok")
    if status not in {"ok", "blocked", "failed", "cancelled", "timeout"}:
        status = "ok"
    payload = getattr(raw_result, "payload", None)
    if not isinstance(payload, dict):
        payload = raw_result if isinstance(raw_result, dict) else {}
    summary = str(getattr(raw_result, "summary", "") or payload.get("summary") or "")
    error_code = getattr(raw_result, "error_code", None)
    return ToolExecutionResult(
        action_id=spec.action_id,
        action_type=spec.action_type,
        status=status,  # type: ignore[arg-type]
        summary=summary or f"Action {spec.action_type} completed.",
        payload=payload,
        error_code=str(error_code) if error_code else None,
    )


def _should_cancel_pending(spec: ToolExecutionSpec, result: ToolExecutionResult) -> bool:
    return spec.cancel_pending_on_failure and result.status in {"failed", "timeout", "cancelled"}


def _emit(
    context: Any,
    event_type: str,
    message: str,
    *,
    spec: ToolExecutionSpec,
    result: ToolExecutionResult | None = None,
) -> None:
    emit = getattr(context, "emit", None)
    if emit is None:
        return
    payload: dict[str, Any] = {
        "action_id": spec.action_id,
        "action_type": spec.action_type,
        "agent_id": spec.agent_id,
        "work_item_id": spec.work_item_id,
    }
    if result is not None:
        payload.update(
            {
                "status": result.status,
                "error_code": result.error_code,
                "elapsed_ms": result.elapsed_ms,
                "summary": result.summary,
            }
        )
    emit(event_type, message, **payload)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _elapsed_ms(started: float) -> int:
    return int((monotonic() - started) * 1000)
