from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from coder_workbench.agent_graph.schema import AgentTaskEnvelope, WorkItem
from coder_workbench.agent_harness import CodeWorkerHarness
from coder_workbench.runtime_capabilities.registries import code_worker_tool_capabilities


class FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeModel:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls = 0

    def invoke(self, prompt: str) -> FakeResponse:
        self.calls += 1
        if len(self.responses) > 1:
            return FakeResponse(self.responses.pop(0))
        return FakeResponse(self.responses[0])


class CodeWorkerLifecycleTests(unittest.TestCase):
    def test_successful_action_has_lifecycle_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "src").mkdir()
            Path(tmp, "src", "app.py").write_text("value = 1\n", encoding="utf-8")
            record = _run_tool_loop(
                tmp,
                FakeModel([_action("read", "read_file", {"path": "src/app.py"}), _final("Read file.")]),
            )

        statuses = record.artifact_payload["requested_actions"][0]["lifecycle_statuses"]
        self.assertEqual(statuses, ["requested", "allowed", "executing", "ok", "recorded"])

    def test_blocked_action_has_blocked_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            record = _run_tool_loop(tmp, FakeModel([_action("escape", "read_file", {"path": "../x.txt"})]))

        statuses = record.artifact_payload["requested_actions"][0]["lifecycle_statuses"]
        self.assertEqual(record.status, "blocked")
        self.assertEqual(statuses, ["requested", "blocked", "recorded"])

    def test_cancel_before_model_call_returns_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            model = FakeModel([_final("Should not run.")])
            record = _run_tool_loop(tmp, model, data={"cancel_requested": True})

        self.assertEqual(model.calls, 0)
        self.assertEqual(record.status, "blocked")
        self.assertIn("cancelled", record.execution_summary)

    def test_cancel_before_action_execution_returns_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "src").mkdir()
            Path(tmp, "src", "app.py").write_text("value = 1\n", encoding="utf-8")
            data: dict = {}

            def emit(event_type: str, _message: str, **_payload) -> None:
                if event_type == "code_worker.loop.action.allowed":
                    data["cancel_requested"] = True

            record = _run_tool_loop(
                tmp,
                FakeModel([_action("read", "read_file", {"path": "src/app.py"})]),
                data=data,
                emit=emit,
            )

        statuses = record.artifact_payload["requested_actions"][0]["lifecycle_statuses"]
        self.assertEqual(record.status, "blocked")
        self.assertIn("cancelled", statuses)

    def test_max_turns_returns_blocked_with_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "src").mkdir()
            Path(tmp, "src", "app.py").write_text("value = 1\n", encoding="utf-8")
            record = _run_tool_loop(tmp, FakeModel([_action("read-repeat", "read_file", {"path": "src/app.py"})]))

        self.assertEqual(record.status, "blocked")
        self.assertEqual(record.artifact_payload["blocker_type"], "timeout")
        self.assertIn("recorded", record.artifact_payload["requested_actions"][0]["lifecycle_statuses"])

    def test_events_do_not_include_huge_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "src").mkdir()
            huge = "x" * 20000
            Path(tmp, "src", "huge.txt").write_text(huge, encoding="utf-8")
            record = _run_tool_loop(
                tmp,
                FakeModel([_action("read", "read_file", {"path": "src/huge.txt"}), _final("Read huge file.")]),
            )

        requested_json = json.dumps(record.artifact_payload["requested_actions"])
        self.assertNotIn("x" * 10000, requested_json)
        self.assertIn("recorded", record.artifact_payload["requested_actions"][0]["lifecycle_statuses"])


def _run_tool_loop(
    repo_root: str,
    model: FakeModel,
    *,
    data: dict | None = None,
    emit=None,
):
    with patch.dict(os.environ, {"CODER_ENABLE_CODE_WORKER_TOOL_LOOP": "1"}):
        return CodeWorkerHarness(model=model).create_execution_result(
            item=_item(),
            envelope=_envelope(),
            repo_root=repo_root,
            run_id="run",
            data={} if data is None else data,
            emit=emit,
        )


def _action(action_id: str, action_type: str, payload: dict, *, risk_level: str = "low") -> str:
    return json.dumps(
        {
            "artifact_type": "harness_action",
            "action_id": action_id,
            "action_type": action_type,
            "payload": payload,
            "reason": "test action",
            "risk_level": risk_level,
        }
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
        capability_set={"tools": [tool.model_dump(mode="json") for tool in code_worker_tool_capabilities()]},
    )


if __name__ == "__main__":
    unittest.main()
