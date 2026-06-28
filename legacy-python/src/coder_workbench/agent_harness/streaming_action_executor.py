from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from coder_workbench.actions import ActionGateway, ActionResult, RunContext
from coder_workbench.agent_harness.action_protocol import HarnessActionRequest, HarnessObservation
from coder_workbench.agent_harness.tool_gate import ToolGate
from coder_workbench.agent_harness.tool_metadata import ToolMetadataRegistry


@dataclass
class _StreamingEntry:
    request: HarnessActionRequest
    started: bool = False
    emitted: bool = False
    future: Future[ActionResult] | None = None
    observation: HarnessObservation | None = None


class StreamingActionExecutor:
    def __init__(
        self,
        *,
        tool_gate: ToolGate,
        action_gateway: ActionGateway,
        run_context: RunContext,
        metadata_registry: ToolMetadataRegistry | None = None,
        emit: Any | None = None,
    ) -> None:
        self.tool_gate = tool_gate
        self.action_gateway = action_gateway
        self.run_context = run_context
        self.metadata_registry = metadata_registry or ToolMetadataRegistry()
        self.emit = emit
        self._pool = ThreadPoolExecutor(max_workers=4)
        self._entries: list[_StreamingEntry] = []
        self._discarded = False

    def add_action(self, request: HarnessActionRequest) -> None:
        if self._discarded:
            raise RuntimeError("StreamingActionExecutor has been discarded.")
        self.metadata_registry.require(request.action_type)
        entry = _StreamingEntry(request=request)
        self._entries.append(entry)
        if self._can_start_early(entry):
            self._start_entry(entry)

    def get_completed_observations(self) -> list[HarnessObservation]:
        completed: list[HarnessObservation] = []
        for entry in self._entries:
            if entry.emitted:
                continue
            if entry.observation is None and entry.future is not None and entry.future.done():
                entry.observation = _observation_from_result(entry.request, entry.future.result())
            if entry.observation is None:
                break
            entry.emitted = True
            completed.append(entry.observation)
        self._release_emitted_prefix()
        return completed

    def discard(self, reason: str) -> list[HarnessObservation]:
        discarded: list[HarnessObservation] = []
        for entry in self._entries:
            if entry.emitted:
                continue
            if entry.future is not None and not entry.future.done():
                entry.future.cancel()
            discarded.append(_synthetic_observation(entry.request, reason))
        self._entries.clear()
        self._discarded = True
        self._pool.shutdown(wait=False, cancel_futures=True)
        return discarded

    def drain(self) -> list[HarnessObservation]:
        observations: list[HarnessObservation] = []
        for entry in self._entries:
            if entry.emitted:
                continue
            if not entry.started:
                self._start_entry(entry, exclusive=True)
            if entry.observation is None:
                if entry.future is not None:
                    entry.observation = _observation_from_result(entry.request, entry.future.result())
                else:
                    entry.observation = self._execute_sync(entry.request)
            entry.emitted = True
            observations.append(entry.observation)
        self._entries.clear()
        self._pool.shutdown(wait=False, cancel_futures=True)
        return observations

    def _can_start_early(self, entry: _StreamingEntry) -> bool:
        metadata = self.metadata_registry.require(entry.request.action_type)
        if not metadata.is_concurrency_safe:
            return False
        for prior in self._entries:
            if prior is entry:
                break
            prior_metadata = self.metadata_registry.require(prior.request.action_type)
            if not prior_metadata.is_concurrency_safe and not prior.emitted:
                return False
        return True

    def _start_entry(self, entry: _StreamingEntry, *, exclusive: bool = False) -> None:
        if entry.started:
            return
        entry.started = True
        decision = self.tool_gate.decide(entry.request)
        if not decision.allowed:
            assert decision.observation is not None
            entry.observation = decision.observation
            return
        assert decision.action_spec is not None
        _emit(
            self.emit,
            "code_worker.streaming_action.started",
            "Streaming action started",
            action_id=entry.request.action_id,
            action_type=entry.request.action_type,
            exclusive=exclusive,
        )
        if exclusive:
            result = self.action_gateway.run(decision.action_spec, run_context=self.run_context)
            entry.observation = _observation_from_result(entry.request, result)
            return
        entry.future = self._pool.submit(self.action_gateway.run, decision.action_spec, run_context=self.run_context)

    def _execute_sync(self, request: HarnessActionRequest) -> HarnessObservation:
        decision = self.tool_gate.decide(request)
        if not decision.allowed:
            assert decision.observation is not None
            return decision.observation
        assert decision.action_spec is not None
        result = self.action_gateway.run(decision.action_spec, run_context=self.run_context)
        return _observation_from_result(request, result)

    def _release_emitted_prefix(self) -> None:
        while self._entries and self._entries[0].emitted:
            self._entries.pop(0)


def _observation_from_result(request: HarnessActionRequest, result: ActionResult) -> HarnessObservation:
    return HarnessObservation(
        action_id=request.action_id,
        action_type=request.action_type,
        status=result.status,
        summary=result.summary or f"{request.action_type} completed with status {result.status}.",
        output_ref=result.output_ref,
        evidence_refs=[f"harness_observation:{request.action_id}", *([result.output_ref] if result.output_ref else [])],
        payload_preview=dict(result.payload),
        error_code=result.error_code,
    )


def _synthetic_observation(request: HarnessActionRequest, reason: str) -> HarnessObservation:
    return HarnessObservation(
        action_id=request.action_id,
        action_type=request.action_type,
        status="blocked",
        summary=f"Streaming action discarded: {reason}",
        evidence_refs=[f"harness_observation:{request.action_id}"],
        error_code="action_discarded",
    )


def _emit(emit: Any | None, event_type: str, message: str, **payload: Any) -> None:
    if emit is not None:
        emit(event_type, message, **{key: value for key, value in payload.items() if value is not None})
