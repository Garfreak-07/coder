from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from coder_workbench.actions import ActionGateway, ActionSpec, RunContext
from coder_workbench.agent_graph.cache import GraphRunCache
from coder_workbench.agent_graph.effects import apply_hidden_effects
from coder_workbench.agent_graph.schema import ExecutionRecord
from coder_workbench.core import default_planner_led_agent_workflow


class CapabilityMatrixTests(unittest.TestCase):
    def test_repo_index_action_records_repo_intelligence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "sample.py").write_text("value = 1\n", encoding="utf-8")
            data: dict[str, object] = {}

            result = ActionGateway().run(
                ActionSpec(action_id="repo-index", action_type="repo_index"),
                run_context=RunContext(run_id="run", repo_root=tmp, data=data),
            )

        self.assertEqual(result.status, "ok")
        self.assertIn("repo_intelligence", result.payload)
        self.assertIn("repo_intelligence", data)

    def test_low_risk_plugin_operation_runs_without_manual_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "README.md").write_text("sample\n", encoding="utf-8")

            result = ActionGateway().run(
                ActionSpec(
                    action_id="plugin-project-index",
                    action_type="call_plugin",
                    input={"operation_id": "project_index", "args": {"max_files": 5}},
                    risk_level="low",
                ),
                run_context=RunContext(run_id="run", repo_root=tmp, data={}),
            )

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.payload["policy"]["risk_level"], "low")
        self.assertFalse(result.payload["policy"]["requires_approval"])

    def test_high_risk_plugin_operation_blocks_before_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "README.md").write_text("sample\n", encoding="utf-8")

            result = ActionGateway().run(
                ActionSpec(
                    action_id="plugin-project-index",
                    action_type="call_plugin",
                    input={"operation_id": "project_index", "args": {"max_files": 5}},
                    risk_level="high",
                ),
                run_context=RunContext(run_id="run", repo_root=tmp, data={}),
            )

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.error_code, "plugin_requires_approval")
        self.assertEqual(result.payload["approval_key"], "plugin:project_index:high")
        self.assertEqual(result.payload["policy"]["risk_level"], "high")

    def test_mcp_call_requires_approval_by_default(self) -> None:
        result = ActionGateway().run(
            ActionSpec(
                action_id="mcp",
                action_type="call_mcp",
                input={"server_command": "fake-mcp", "tool_name": "read_file"},
            ),
            run_context=RunContext(run_id="run", repo_root="."),
        )

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.error_code, "mcp_requires_approval")
        self.assertEqual(result.payload["policy"]["operation_id"], "mcp_call")

    def test_run_command_sandbox_accepts_argv_without_shell(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            sandbox = root / "sandbox"
            repo.mkdir()
            sandbox.mkdir()

            result = ActionGateway().run(
                ActionSpec(
                    action_id="argv-check",
                    action_type="run_command_sandbox",
                    input={
                        "argv": [sys.executable, "-c", "print('argv-ok')"],
                        "shell": False,
                        "cwd": ".",
                    },
                ),
                run_context=RunContext(run_id="run", repo_root=repo, sandbox_root=sandbox),
            )

        self.assertEqual(result.status, "ok")
        self.assertIn("argv-ok", result.payload["result"]["output"])
        self.assertFalse(result.payload["result"]["policy"]["requires_approval"])

    def test_shell_command_boundary_requires_approval_outside_sandbox(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = ActionGateway().run(
                ActionSpec(
                    action_id="shell-check",
                    action_type="run_command",
                    input={
                        "command": "echo ok && echo done",
                        "shell": True,
                        "require_approval": False,
                    },
                ),
                run_context=RunContext(run_id="run", repo_root=tmp, data={}),
            )

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.error_code, "command_requires_approval")
        self.assertEqual(result.payload["result"]["policy"]["risk"], "medium")

    def test_unknown_requested_operation_becomes_failed_runtime_action(self) -> None:
        cache = GraphRunCache(round=1)
        cache.record_execution(
            ExecutionRecord(
                work_item_id="executor-work",
                merge_index=1,
                agent_id="executor",
                status="completed",
                execution_summary="Requested unsupported operation.",
                execution_result_ref="execution_result_executor-work",
                artifact_payload={
                    "artifact_type": "execution_result",
                    "status": "completed",
                    "summary": "Requested unsupported operation.",
                    "requested_actions": [
                        {"action_type": "unsupported_operation", "operation_id": "unknown.op"}
                    ],
                },
            )
        )

        with tempfile.TemporaryDirectory() as tmp:
            records = apply_hidden_effects(
                agent_workflow=default_planner_led_agent_workflow(),
                cache=cache,
                repo_root=tmp,
                scopes=[],
                data={"run_id": "run"},
            )

        effect = next(record for record in records if record["effect_type"] == "runtime_action")
        self.assertEqual(effect["status"], "failed")
        self.assertEqual(effect["error_code"], "unknown_action_type")
        self.assertEqual(effect["action_spec"]["action_type"], "unsupported_operation")


if __name__ == "__main__":
    unittest.main()
