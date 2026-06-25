from __future__ import annotations

import json
import os
import subprocess
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


class CodeWorkerPatchWorkflowTests(unittest.TestCase):
    def test_apply_patch_auto_inspects_git_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _git_repo(tmp)
            record = _run_tool_loop(
                tmp,
                [
                    _action(
                        "patch",
                        "apply_patch_sandbox",
                        {
                            "approved": True,
                            "changes": [{"path": "sample.py", "action": "update", "content": "value = 2\n"}],
                        },
                    ),
                    _final("Patched file."),
                ],
            )

        requested = record.artifact_payload["requested_actions"]
        self.assertEqual(record.status, "completed")
        self.assertIn("sample.py", record.artifact_payload["changed_files"])
        self.assertEqual([item["action_type"] for item in requested[:2]], ["apply_patch_sandbox", "inspect_git_diff"])

    def test_patch_success_records_changed_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp, "repo")
            sandbox = Path(tmp, "sandbox")
            root.mkdir()
            sandbox.mkdir()
            Path(root, "sample.py").write_text("value = 1\n", encoding="utf-8")
            Path(sandbox, "sample.py").write_text("value = 1\n", encoding="utf-8")
            record = _run_tool_loop(
                str(root),
                [
                    _action(
                        "patch",
                        "apply_patch_sandbox",
                        {"changes": [{"path": "sample.py", "action": "update", "content": "value = 2\n"}]},
                    ),
                    _final("Patched file."),
                ],
                sandbox_root=str(sandbox),
            )

        self.assertEqual(record.status, "completed")
        self.assertEqual(record.artifact_payload["changed_files"], ["sample.py"])
        self.assertTrue(record.artifact_payload["patch_refs"])

    def test_patch_failure_requires_reread_before_next_patch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp, "repo")
            sandbox = Path(tmp, "sandbox")
            root.mkdir()
            sandbox.mkdir()
            Path(root, "sample.py").write_text("value = 1\n", encoding="utf-8")
            Path(sandbox, "sample.py").write_text("value = 1\n", encoding="utf-8")
            good_patch = {"changes": [{"path": "sample.py", "action": "update", "content": "value = 2\n"}]}
            record = _run_tool_loop(
                str(root),
                [
                    _action("bad-patch", "apply_patch_sandbox", {"changes": [{"path": "missing.py", "action": "update", "content": "x\n"}]}),
                    _action("blocked-retry", "apply_patch_sandbox", good_patch),
                    _action("reread", "read_file", {"path": "sample.py"}),
                    _action("good-patch", "apply_patch_sandbox", good_patch),
                    _final("Patched after reread."),
                ],
                sandbox_root=str(sandbox),
            )

        requested = record.artifact_payload["requested_actions"]
        workflow_blocks = [item for item in requested if item["action_type"] == "patch_workflow"]
        self.assertEqual(record.status, "completed")
        self.assertEqual(workflow_blocks[0]["error_code"], "patch_requires_reread")
        self.assertIn("sample.py", record.artifact_payload["changed_files"])

    def test_completed_after_failed_patch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp, "repo")
            sandbox = Path(tmp, "sandbox")
            root.mkdir()
            sandbox.mkdir()
            record = _run_tool_loop(
                str(root),
                [
                    _action("bad-patch", "apply_patch_sandbox", {"changes": [{"path": "missing.py", "action": "update", "content": "x\n"}]}),
                    _final("Ignored patch failure."),
                ],
                sandbox_root=str(sandbox),
            )

        self.assertEqual(record.status, "blocked")
        self.assertEqual(record.artifact_payload["blocker_type"], "schema_validation_failed")
        self.assertTrue(any(item.get("error_code") == "patch_failed" for item in record.artifact_payload["requested_actions"]))


def _run_tool_loop(
    repo_root: str,
    responses: list[str],
    *,
    sandbox_root: str | None = None,
):
    with patch.dict(os.environ, {"CODER_ENABLE_CODE_WORKER_TOOL_LOOP": "1"}):
        return CodeWorkerHarness(model=FakeModel(responses)).create_execution_result(
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
