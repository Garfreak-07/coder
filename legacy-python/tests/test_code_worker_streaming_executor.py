from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from coder_workbench.actions import ActionResult, RunContext
from coder_workbench.agent_graph.schema import AgentTaskEnvelope, WorkItem
from coder_workbench.agent_harness import CodeWorkerHarness, HarnessActionRequest, StreamingActionExecutor, ToolGate
from coder_workbench.runtime_capabilities.registries import code_worker_tool_capabilities


class RecordingGateway:
    def __init__(self, delay_by_action_id: dict[str, float] | None = None) -> None:
        self.calls: list[str] = []
        self.delay_by_action_id = delay_by_action_id or {}

    def run(self, spec, *, run_context):
        self.calls.append(spec.action_id)
        delay = self.delay_by_action_id.get(spec.action_id, 0)
        if delay:
            time.sleep(delay)
        return ActionResult(
            status="ok",
            summary=f"{spec.action_type} ok",
            payload={"action_id": spec.action_id},
        )


class FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeModel:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)

    def invoke(self, prompt: str) -> FakeResponse:
        if len(self.responses) > 1:
            return FakeResponse(self.responses.pop(0))
        return FakeResponse(self.responses[0])


class CodeWorkerStreamingExecutorTests(unittest.TestCase):
    def test_streaming_executor_runs_safe_read_actions_early(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            executor, gateway = _executor(tmp)
            executor.add_action(_request("read", "read_file", {"path": "src/app.py"}))
            observations = _wait_for_completed(executor)

        self.assertEqual(gateway.calls, ["read"])
        self.assertEqual(observations[0].action_id, "read")

    def test_exclusive_action_waits_for_prior_safe_batch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            executor, gateway = _executor(tmp)
            executor.add_action(_request("read", "read_file", {"path": "src/app.py"}))
            executor.add_action(
                _request("command", "run_command_sandbox", {"argv": [sys.executable, "-c", "print(1)"]})
            )
            _wait_for_completed(executor)
            self.assertEqual(gateway.calls, ["read"])
            observations = executor.drain()

        self.assertEqual([observation.action_id for observation in observations], ["command"])
        self.assertEqual(gateway.calls, ["read", "command"])

    def test_discard_creates_synthetic_observations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            executor, _gateway = _executor(tmp)
            executor.add_action(
                _request("command", "run_command_sandbox", {"argv": [sys.executable, "-c", "print(1)"]})
            )
            observations = executor.discard("model fallback")

        self.assertEqual(observations[0].action_id, "command")
        self.assertEqual(observations[0].status, "blocked")
        self.assertEqual(observations[0].error_code, "action_discarded")

    def test_discard_releases_pending_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            executor, _gateway = _executor(tmp)
            executor.add_action(
                _request("command", "run_command_sandbox", {"argv": [sys.executable, "-c", "print(1)"]})
            )
            executor.discard("cancel")

        self.assertEqual(executor.get_completed_observations(), [])
        self.assertEqual(executor.drain(), [])

    def test_observation_order_is_stable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            executor, _gateway = _executor(tmp, delay_by_action_id={"read-1": 0.05})
            executor.add_action(_request("read-1", "read_file", {"path": "src/app.py"}))
            executor.add_action(_request("search-2", "search_files", {"query": "value", "paths": ["src"]}))
            observations = executor.drain()

        self.assertEqual([observation.action_id for observation in observations], ["read-1", "search-2"])

    def test_non_streaming_loop_still_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "src").mkdir()
            Path(tmp, "src", "app.py").write_text("value = 1\n", encoding="utf-8")
            with patch.dict(os.environ, {"CODER_ENABLE_CODE_WORKER_TOOL_LOOP": ""}):
                record = CodeWorkerHarness(model=FakeModel([_final("Legacy path.")])).create_execution_result(
                    item=_item(),
                    envelope=_envelope(),
                    repo_root=tmp,
                )

        self.assertEqual(record.status, "completed")
        self.assertEqual(record.execution_summary, "Legacy path.")


def _executor(
    repo_root: str,
    *,
    delay_by_action_id: dict[str, float] | None = None,
) -> tuple[StreamingActionExecutor, RecordingGateway]:
    root = Path(repo_root)
    Path(root, "src").mkdir(exist_ok=True)
    Path(root, "src", "app.py").write_text("value = 1\n", encoding="utf-8")
    run_context = RunContext(run_id="run", repo_root=repo_root, data={})
    capability_set = {"tools": [tool.model_dump(mode="json") for tool in code_worker_tool_capabilities()]}
    gateway = RecordingGateway(delay_by_action_id)
    executor = StreamingActionExecutor(
        tool_gate=ToolGate(run_context=run_context, capability_set=capability_set),
        action_gateway=gateway,  # type: ignore[arg-type]
        run_context=run_context,
    )
    return executor, gateway


def _wait_for_completed(executor: StreamingActionExecutor):
    observations = []
    for _ in range(50):
        observations = executor.get_completed_observations()
        if observations:
            return observations
        time.sleep(0.01)
    return observations


def _request(action_id: str, action_type: str, payload: dict) -> HarnessActionRequest:
    return HarnessActionRequest(
        action_id=action_id,
        action_type=action_type,
        payload=payload,
        reason="test action",
        risk_level="low",
    )


def _final(summary: str) -> str:
    return json.dumps({"artifact_type": "execution_result", "status": "completed", "summary": summary})


def _item() -> WorkItem:
    return WorkItem(
        work_item_id="executor-work",
        merge_index=1,
        assignee_agent_id="executor",
        task_summary="Fix src/app.py.",
    )


def _envelope() -> AgentTaskEnvelope:
    return AgentTaskEnvelope(
        round=1,
        work_item_id="executor-work",
        merge_index=1,
        assigned_agent_id="executor",
        task_summary="Fix src/app.py.",
        planner_order_ref="planner_order_round_1",
    )


if __name__ == "__main__":
    unittest.main()
