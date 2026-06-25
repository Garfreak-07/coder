from __future__ import annotations

import json
import os
import sys
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

    def invoke(self, prompt: str) -> FakeResponse:
        if len(self.responses) > 1:
            return FakeResponse(self.responses.pop(0))
        return FakeResponse(self.responses[0])


class CodeWorkerCancelTimeoutTests(unittest.TestCase):
    def test_command_timeout_returns_blocked_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp, "repo")
            sandbox = Path(tmp, "sandbox")
            root.mkdir()
            sandbox.mkdir()
            record = _run_tool_loop(
                str(root),
                FakeModel(
                    [
                        _action(
                            "slow-check",
                            "run_command_sandbox",
                            {
                                "argv": [sys.executable, "-c", "import time; time.sleep(2)"],
                                "timeout_seconds": 1,
                            },
                        ),
                        _final("Timed out."),
                    ]
                ),
                sandbox_root=str(sandbox),
            )

        check = record.artifact_payload["verification"]["checks_run"][0]
        action = record.artifact_payload["requested_actions"][0]
        self.assertEqual(record.status, "blocked")
        self.assertEqual(check["status"], "blocked")
        self.assertEqual(action["error_code"], "command_timeout")
        self.assertIn("recorded", action["lifecycle_statuses"])


def _run_tool_loop(
    repo_root: str,
    model: FakeModel,
    *,
    sandbox_root: str | None = None,
):
    with patch.dict(os.environ, {"CODER_ENABLE_CODE_WORKER_TOOL_LOOP": "1"}):
        return CodeWorkerHarness(model=model).create_execution_result(
            item=_item(),
            envelope=_envelope(),
            repo_root=repo_root,
            sandbox_root=sandbox_root,
            run_id="run",
            data={},
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
        task_summary="Run slow check.",
    )


def _envelope() -> AgentTaskEnvelope:
    return AgentTaskEnvelope(
        round=1,
        work_item_id="executor-work",
        merge_index=1,
        assigned_agent_id="executor",
        task_summary="Run slow check.",
        planner_order_ref="planner_order_round_1",
        capability_set={"tools": [tool.model_dump(mode="json") for tool in code_worker_tool_capabilities()]},
    )


if __name__ == "__main__":
    unittest.main()
