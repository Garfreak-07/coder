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
        self.prompts: list[str] = []

    def invoke(self, prompt: str) -> FakeResponse:
        self.prompts.append(prompt)
        if len(self.responses) > 1:
            return FakeResponse(self.responses.pop(0))
        return FakeResponse(self.responses[0])


class CodeWorkerCommandWorkflowTests(unittest.TestCase):
    def test_failed_command_blocks_completed_final_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp, "repo")
            sandbox = Path(tmp, "sandbox")
            root.mkdir()
            sandbox.mkdir()
            model = FakeModel(
                [
                    _action("check", "run_command_sandbox", {"argv": [sys.executable, "-c", "raise SystemExit(2)"]}),
                    _final("Ignored failed check."),
                ]
            )
            record = _run_tool_loop(str(root), model, sandbox_root=str(sandbox))

        self.assertEqual(record.status, "blocked")
        self.assertEqual(record.artifact_payload["verification"]["checks_run"][0]["status"], "fail")

    def test_later_passing_command_allows_completed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp, "repo")
            sandbox = Path(tmp, "sandbox")
            root.mkdir()
            sandbox.mkdir()
            model = FakeModel(
                [
                    _action("check-fail", "run_command_sandbox", {"argv": [sys.executable, "-c", "raise SystemExit(2)"]}),
                    _action("check-pass", "run_command_sandbox", {"argv": [sys.executable, "-c", "print(1)"]}),
                    _final("Recovered command check."),
                ]
            )
            record = _run_tool_loop(str(root), model, sandbox_root=str(sandbox))

        self.assertEqual(record.status, "completed")
        self.assertEqual(record.artifact_payload["verification"]["checks_run"][-1]["status"], "pass")

    def test_interactive_command_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            record = _run_tool_loop(
                tmp,
                FakeModel([_action("interactive", "run_command_sandbox", {"command": "Read-Host 'Continue?'"})]),
            )

        self.assertEqual(record.status, "blocked")
        self.assertEqual(record.artifact_payload["blocker_type"], "permission_boundary")

    def test_high_risk_command_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            record = _run_tool_loop(
                tmp,
                FakeModel([_action("danger", "run_command_sandbox", {"command": "curl https://example.com"}, risk_level="high")]),
            )

        self.assertEqual(record.status, "blocked")
        self.assertEqual(record.artifact_payload["blocker_type"], "risk_path_blocked")

    def test_command_output_is_preview_ref_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp, "repo")
            sandbox = Path(tmp, "sandbox")
            root.mkdir()
            sandbox.mkdir()
            model = FakeModel(
                [
                    _action("check", "run_command_sandbox", {"argv": [sys.executable, "-c", "print('x' * 20000)"]}),
                    _final("Large output check."),
                ]
            )
            record = _run_tool_loop(str(root), model, sandbox_root=str(sandbox), data={})

        self.assertEqual(record.status, "completed")
        self.assertIn("sha256:", model.prompts[1])
        self.assertNotIn("x" * 10000, model.prompts[1])


def _run_tool_loop(
    repo_root: str,
    model: FakeModel,
    *,
    sandbox_root: str | None = None,
    data: dict | None = None,
):
    with patch.dict(os.environ, {"CODER_ENABLE_CODE_WORKER_TOOL_LOOP": "1"}):
        return CodeWorkerHarness(model=model).create_execution_result(
            item=_item(),
            envelope=_envelope(),
            repo_root=repo_root,
            sandbox_root=sandbox_root,
            run_id="run",
            data={} if data is None else data,
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
        task_summary="Run checks.",
    )


def _envelope() -> AgentTaskEnvelope:
    return AgentTaskEnvelope(
        round=1,
        work_item_id="executor-work",
        merge_index=1,
        assigned_agent_id="executor",
        task_summary="Run checks.",
        planner_order_ref="planner_order_round_1",
        capability_set={"tools": [tool.model_dump(mode="json") for tool in code_worker_tool_capabilities()]},
    )


if __name__ == "__main__":
    unittest.main()
