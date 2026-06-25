from __future__ import annotations

import json
import os
import subprocess
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


class CodeWorkerClaudeParityAcceptanceTests(unittest.TestCase):
    def test_read_patch_diff_command_final_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _git_repo(tmp)
            record = _run_tool_loop(
                tmp,
                FakeModel(
                    [
                        _action("read", "read_file", {"path": "sample.py"}),
                        _action(
                            "patch",
                            "apply_patch_sandbox",
                            {
                                "approved": True,
                                "changes": [{"path": "sample.py", "action": "update", "content": "value = 2\n"}],
                            },
                        ),
                        _action("check", "run_command_sandbox", {"argv": [sys.executable, "-c", "print(1)"]}),
                        _final("Implemented and verified."),
                    ]
                ),
                sandbox_root=tmp,
            )

        self.assertEqual(record.status, "completed")
        self.assertEqual(record.artifact_payload["changed_files"], ["sample.py"])
        self.assertTrue(record.artifact_payload["patch_refs"])
        self.assertEqual(record.artifact_payload["verification"]["status"], "pass")
        self.assertEqual(record.artifact_payload["verification"]["checks_run"][-1]["status"], "pass")
        self.assertTrue(record.artifact_payload["evidence_refs"])

    def test_failed_command_repair_pass_final_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _git_repo(tmp)
            record = _run_tool_loop(
                tmp,
                FakeModel(
                    [
                        _action("check-fail", "run_command_sandbox", {"argv": [sys.executable, "-c", "raise SystemExit(2)"]}),
                        _action(
                            "patch",
                            "apply_patch_sandbox",
                            {
                                "approved": True,
                                "changes": [{"path": "sample.py", "action": "update", "content": "value = 3\n"}],
                            },
                        ),
                        _action("check-pass", "run_command_sandbox", {"argv": [sys.executable, "-c", "print(1)"]}),
                        _final("Repaired and verified."),
                    ]
                ),
                sandbox_root=tmp,
            )

        checks = record.artifact_payload["verification"]["checks_run"]
        self.assertEqual(record.status, "completed")
        self.assertEqual([check["status"] for check in checks], ["fail", "pass"])
        self.assertEqual(record.artifact_payload["verification"]["remaining_work"], [])

    def test_model_lies_about_changed_files_is_not_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "sample.py").write_text("value = 1\n", encoding="utf-8")
            record = _run_tool_loop(
                tmp,
                FakeModel(
                    [
                        _action("read", "read_file", {"path": "sample.py"}),
                        json.dumps(
                            {
                                "artifact_type": "execution_result",
                                "status": "completed",
                                "summary": "Done.",
                                "changed_files": ["fake.py"],
                            }
                        ),
                    ]
                ),
            )

        self.assertEqual(record.status, "blocked")
        self.assertNotIn("fake.py", record.artifact_payload["changed_files"])

    def test_planner_only_output_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            record = _run_tool_loop(
                tmp,
                FakeModel([json.dumps({"artifact_type": "planner_decision", "task_done": False, "next_action": "continue", "reason": "no"})]),
            )

        self.assertEqual(record.status, "blocked")
        self.assertEqual(record.artifact_payload["blocker_type"], "permission_boundary")

    def test_large_output_uses_preview_and_refs_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp, "repo")
            sandbox = Path(tmp, "sandbox")
            root.mkdir()
            sandbox.mkdir()
            model = FakeModel(
                [
                    _action("large", "run_command_sandbox", {"argv": [sys.executable, "-c", "print('x' * 20000)"]}),
                    _final("Large output checked."),
                ]
            )
            record = _run_tool_loop(str(root), model, sandbox_root=str(sandbox))

        self.assertEqual(record.status, "completed")
        self.assertIn("sha256:", model.prompts[1])
        self.assertNotIn("x" * 10000, model.prompts[1])


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


def _git_repo(path: str) -> None:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    Path(path, "sample.py").write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "sample.py"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=path, check=True, capture_output=True, text=True)


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
        task_summary="Fix sample.py.",
    )


def _envelope() -> AgentTaskEnvelope:
    return AgentTaskEnvelope(
        round=1,
        work_item_id="executor-work",
        merge_index=1,
        assigned_agent_id="executor",
        task_summary="Fix sample.py.",
        planner_order_ref="planner_order_round_1",
        capability_set={"tools": [tool.model_dump(mode="json") for tool in code_worker_tool_capabilities()]},
    )


if __name__ == "__main__":
    unittest.main()
