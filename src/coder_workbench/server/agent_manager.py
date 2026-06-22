from __future__ import annotations

from dataclasses import dataclass, field
from queue import Empty, Queue
from threading import Lock, Thread
from typing import Any, Literal
from uuid import uuid4

from coder_workbench.agent_graph import AgentGraphRunner
from coder_workbench.core import AgentWorkflowSpec
from coder_workbench.runtime import RunEvent, RunResult
from coder_workbench.runtime_kernel import RunControl
from coder_workbench.server.storage import RunStore


LiveStatus = Literal["queued", "running", "paused", "cancelling", "cancelled", "completed", "blocked", "failed"]


@dataclass
class LiveAgentRun:
    id: str
    agent_workflow: AgentWorkflowSpec
    repo_root: str
    request: str
    initial_data: dict[str, Any]
    status: LiveStatus = "queued"
    events: list[RunEvent] = field(default_factory=list)
    queue: Queue[RunEvent | None] = field(default_factory=Queue)
    run_control: RunControl = field(default_factory=RunControl)
    result: RunResult | None = None
    stored_run_id: str | None = None
    error: str | None = None


class AgentGraphRunManager:
    def __init__(self, store: RunStore, runtime_settings_loader: Any | None = None) -> None:
        self.store = store
        self.runtime_settings_loader = runtime_settings_loader
        self._runs: dict[str, LiveAgentRun] = {}
        self._lock = Lock()
        self._load_persisted_live_runs()

    def start(
        self,
        agent_workflow: AgentWorkflowSpec,
        repo_root: str,
        request: str,
        initial_data: dict[str, Any],
    ) -> LiveAgentRun:
        live = LiveAgentRun(
            id=str(uuid4()),
            agent_workflow=agent_workflow,
            repo_root=repo_root,
            request=request,
            initial_data=dict(initial_data),
        )
        live.initial_data["run_id"] = live.id
        with self._lock:
            self._runs[live.id] = live
        self._persist_live(live)
        thread = Thread(target=self._execute, args=(live,), daemon=True)
        thread.start()
        return live

    def get(self, run_id: str) -> LiveAgentRun:
        with self._lock:
            if run_id not in self._runs:
                raise KeyError(run_id)
            return self._runs[run_id]

    def submit_planner_response(
        self,
        run_id: str,
        *,
        response: str,
        data: dict[str, Any] | None = None,
    ) -> LiveAgentRun:
        run = self.get(run_id)
        if run.status != "blocked" or not run.result or run.result.status_code != "planner_ask_human":
            raise ValueError("run is not waiting for a Planner human response")
        checkpoint_data = dict((run.result.resume_checkpoint or {}).get("data", {}))
        checkpoint_data["planner_human_response"] = {
            "response": response,
            "data": data or {},
        }
        checkpoint_data.pop("planner_decision", None)
        checkpoint_data["resume_mode"] = "planner_response"
        run.initial_data = checkpoint_data
        run.status = "queued"
        run.error = None
        run.queue = Queue()
        prior_events = list(run.events)
        thread = Thread(target=self._execute, args=(run, prior_events), daemon=True)
        thread.start()
        return run

    def pause(self, run_id: str) -> LiveAgentRun:
        run = self.get(run_id)
        if run.status not in {"queued", "running"}:
            raise ValueError("run cannot be paused from its current status")
        run.run_control.request_pause()
        run.status = "paused"
        self._persist_live(run)
        return run

    def resume(self, run_id: str) -> LiveAgentRun:
        run = self.get(run_id)
        if run.status != "paused":
            raise ValueError("run is not paused")
        run.run_control.request_resume()
        run.status = "running" if run.result is None else run.result.status
        self._persist_live(run)
        return run

    def cancel(self, run_id: str) -> LiveAgentRun:
        run = self.get(run_id)
        if run.status not in {"queued", "running", "paused", "cancelling"}:
            raise ValueError("run cannot be cancelled from its current status")
        run.run_control.request_cancel()
        run.status = "cancelling"
        self._persist_live(run)
        return run

    def heartbeat(self, run_id: str) -> dict[str, Any]:
        run = self.get(run_id)
        return self._heartbeat_payload(run)

    def _heartbeat_payload(self, run: LiveAgentRun) -> dict[str, Any]:
        diagnostics = run.run_control.diagnostics()
        return {
            "run_id": run.id,
            "status": run.status,
            "last_heartbeat_at": diagnostics.get("last_heartbeat_at"),
            "location": diagnostics.get("location"),
            "active_round": diagnostics.get("active_round"),
            "active_wave": diagnostics.get("active_wave"),
            "active_work_item_ids": diagnostics.get("active_work_item_ids", []),
        }

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {
                    "id": run.id,
                    "workflow_id": run.agent_workflow.id,
                    "runtime_type": "agent_graph",
                    "repo_root": run.repo_root,
                    "request": run.request,
                    "status": run.status,
                    "events": len(run.events),
                    "stored_run_id": run.stored_run_id,
                    "error": run.error,
                    "status_reason": run.result.status_reason if run.result else run.error,
                    "status_code": run.result.status_code if run.result else None,
                    "heartbeat": self._heartbeat_payload(run),
                    "approval_required": False,
                }
                for run in self._runs.values()
            ]

    def stream(self, run_id: str):
        run = self.get(run_id)
        sent = 0
        while sent < len(run.events):
            yield run.events[sent]
            sent += 1
        while True:
            try:
                event = run.queue.get(timeout=1)
            except Empty:
                if run.status not in {"queued", "running"}:
                    break
                continue
            if event is None:
                break
            yield event

    def _load_persisted_live_runs(self) -> None:
        for payload in self.store.list_live():
            if payload.get("runtime_type") != "agent_graph":
                continue
            try:
                agent_workflow = AgentWorkflowSpec.model_validate(payload["agent_workflow"])
                result_payload = payload.get("result")
                result = RunResult.model_validate(result_payload) if isinstance(result_payload, dict) else None
                events = [
                    RunEvent.model_validate(event)
                    for event in payload.get("events", [])
                    if isinstance(event, dict)
                ]
                status = payload.get("status", "failed")
                if status in {"queued", "running"}:
                    status = "failed"
                live = LiveAgentRun(
                    id=str(payload["id"]),
                    agent_workflow=agent_workflow,
                    repo_root=str(payload["repo_root"]),
                    request=str(payload["request"]),
                    initial_data=dict(payload.get("initial_data", {})),
                    status=status,
                    events=events,
                    run_control=RunControl(),
                    result=result,
                    stored_run_id=payload.get("stored_run_id"),
                    error=payload.get("error"),
                )
                self._runs[live.id] = live
            except Exception:
                continue

    def _execute(self, run: LiveAgentRun, prior_events: list[RunEvent] | None = None) -> None:
        if run.status != "paused":
            run.status = "running"

        def sink(event: RunEvent) -> None:
            run.events.append(event)
            self._update_heartbeat_from_event(run, event)
            run.queue.put(event)
            self._persist_live(run)

        try:
            runtime_settings = self.runtime_settings_loader() if self.runtime_settings_loader else None
            result = AgentGraphRunner(
                run.agent_workflow,
                event_sink=sink,
                runtime_settings=runtime_settings,
            ).run(
                request=run.request,
                repo_root=run.repo_root,
                initial_data=run.initial_data,
                prior_events=prior_events,
                run_control=run.run_control,
            )
            run.result = result
            stored = self.store.save(
                workflow_id=run.agent_workflow.id,
                repo_root=run.repo_root,
                request=run.request,
                result=result,
            )
            run.stored_run_id = stored.id
            run.status = "cancelled" if result.status == "cancelled" else result.status
        except Exception as exc:  # pragma: no cover - background boundary
            run.status = "failed"
            run.error = str(exc)
        finally:
            self._persist_live(run)
            run.queue.put(None)

    def _persist_live(self, run: LiveAgentRun) -> None:
        self.store.save_live(
            {
                "id": run.id,
                "runtime_type": "agent_graph",
                "agent_workflow": run.agent_workflow.model_dump(mode="json", by_alias=True, exclude_none=True),
                "repo_root": run.repo_root,
                "request": run.request,
                "initial_data": run.initial_data,
                "status": run.status,
                "events": [event.model_dump(mode="json") for event in run.events],
                "result": run.result.model_dump(mode="json") if run.result else None,
                "stored_run_id": run.stored_run_id,
                "error": run.error,
                "run_control": run.run_control.diagnostics(),
            }
        )

    def _update_heartbeat_from_event(self, run: LiveAgentRun, event: RunEvent) -> None:
        payload = event.payload
        round_number = payload.get("round") or payload.get("active_round")
        wave_index = payload.get("wave_index") or payload.get("active_wave")
        work_item_ids = payload.get("work_item_ids") or payload.get("active_work_item_ids")
        if work_item_ids is None and payload.get("work_item_id"):
            work_item_ids = [payload.get("work_item_id")]
        run.run_control.heartbeat(
            event.type,
            round_number=int(round_number) if isinstance(round_number, int) else None,
            wave_index=int(wave_index) if isinstance(wave_index, int) else None,
            active_work_item_ids=[str(item) for item in work_item_ids] if isinstance(work_item_ids, list) else None,
        )
