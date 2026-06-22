from __future__ import annotations

import tempfile
import time
import unittest
from unittest.mock import patch

from coder_workbench.core import default_planner_led_agent_workflow
from coder_workbench.runtime import RunEvent, RunResult
from coder_workbench.runtime_kernel import RunCancelled
from coder_workbench.server.agent_manager import AgentGraphRunManager
from coder_workbench.server.storage import RunStore


class LiveRunLifecycleTests(unittest.TestCase):
    def test_cancel_running_run_persists_cancelled_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = AgentGraphRunManager(RunStore(tmp))
            with patch("coder_workbench.server.agent_manager.AgentGraphRunner", SlowFakeRunner):
                run = manager.start(default_planner_led_agent_workflow(), tmp, "Slow run.", {})
                _wait_for_status(manager, run.id, {"running"})
                manager.cancel(run.id)
                final = _wait_for_status(manager, run.id, {"cancelled"})

        self.assertEqual(final.status, "cancelled")
        self.assertEqual(final.result.status, "cancelled")

    def test_pause_and_resume_running_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = AgentGraphRunManager(RunStore(tmp))
            with patch("coder_workbench.server.agent_manager.AgentGraphRunner", SlowFakeRunner):
                run = manager.start(default_planner_led_agent_workflow(), tmp, "Slow run.", {})
                _wait_for_status(manager, run.id, {"running"})
                manager.pause(run.id)
                paused = manager.get(run.id)
                self.assertEqual(paused.status, "paused")
                manager.resume(run.id)
                final = _wait_for_status(manager, run.id, {"completed"})

        self.assertEqual(final.status, "completed")
        self.assertEqual(final.result.status, "completed")

    def test_restart_marks_persisted_running_run_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = RunStore(tmp)
            store.save_live(
                {
                    "id": "live",
                    "runtime_type": "agent_graph",
                    "agent_workflow": default_planner_led_agent_workflow().model_dump(mode="json", by_alias=True),
                    "repo_root": tmp,
                    "request": "request",
                    "initial_data": {},
                    "status": "running",
                    "events": [],
                    "result": None,
                    "stored_run_id": None,
                    "error": None,
                }
            )
            manager = AgentGraphRunManager(store)

        self.assertEqual(manager.get("live").status, "failed")


class SlowFakeRunner:
    def __init__(self, *args, event_sink=None, **kwargs) -> None:
        self.event_sink = event_sink

    def run(self, request, repo_root, initial_data=None, prior_events=None, run_control=None, **kwargs) -> RunResult:
        events: list[RunEvent] = []
        try:
            for index in range(20):
                if run_control is not None:
                    run_control.checkpoint("fake_step", round_number=1, active_work_item_ids=["work"])
                event = RunEvent(type="agent_graph.run.heartbeat", message="heartbeat", payload={"round": 1, "work_item_id": "work"})
                events.append(event)
                if self.event_sink is not None:
                    self.event_sink(event)
                time.sleep(0.01)
        except RunCancelled as exc:
            return RunResult(
                status="cancelled",
                data={"run_control": run_control.diagnostics() if run_control else {}},
                summaries={},
                artifacts={},
                events=events,
                estimated_tokens_used=0,
                agent_calls=0,
                tool_calls=0,
                status_reason=str(exc),
                status_code="run_cancelled",
            )
        return RunResult(
            status="completed",
            data={"run_control": run_control.diagnostics() if run_control else {}},
            summaries={},
            artifacts={},
            events=events,
            estimated_tokens_used=0,
            agent_calls=0,
            tool_calls=0,
        )


def _wait_for_status(manager: AgentGraphRunManager, run_id: str, statuses: set[str]):
    current = manager.get(run_id)
    for _ in range(100):
        current = manager.get(run_id)
        if current.status in statuses:
            return current
        time.sleep(0.02)
    return current


if __name__ == "__main__":
    unittest.main()
