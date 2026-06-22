from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from coder_workbench.actions import ActionGateway, ActionSpec, ResultBudget, RunContext


class ActionGatewayToolExecutionTests(unittest.TestCase):
    def test_gateway_emits_tool_execution_events_when_enabled(self) -> None:
        events: list[tuple[str, dict[str, Any]]] = []

        def emit(event_type: str, message: str, **payload: Any) -> None:
            events.append((event_type, {"message": message, **payload}))

        result = ActionGateway(
            command_service_factory=lambda repo_root, scopes, data: FakeCommandService(output="ok"),
            enable_tool_execution_service=True,
        ).run(
            ActionSpec(
                action_id="cmd",
                action_type="run_command",
                input={"command": "echo ok"},
            ),
            run_context=RunContext(
                run_id="run",
                repo_root=".",
                data={"preapprove_all": True},
                emit=emit,
            ),
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual(
            [event[0] for event in events],
            ["action.execution.started", "action.execution.completed"],
        )
        self.assertEqual(result.payload["tool_execution"]["status"], "ok")

    def test_large_tool_output_is_externalized_when_service_enabled(self) -> None:
        data: dict[str, Any] = {"preapprove_all": True}
        large_output = "0123456789" * 50

        result = ActionGateway(
            command_service_factory=lambda repo_root, scopes, data: FakeCommandService(output=large_output),
            enable_tool_execution_service=True,
            result_budget=ResultBudget(max_inline_chars=100, preview_chars=30),
        ).run(
            ActionSpec(
                action_id="cmd-large",
                action_type="run_command",
                input={"command": "emit large output"},
            ),
            run_context=RunContext(run_id="run", repo_root=".", data=data),
        )

        output = result.payload["result"]["output"]
        self.assertEqual(result.status, "ok")
        self.assertIn("blob_id", output)
        self.assertTrue(output["blob_id"].startswith("sha256:"))
        self.assertEqual(output["original_chars"], len(large_output))
        self.assertIn(output["blob_id"], data["pending_blob_writes"])
        self.assertEqual(data["pending_blob_writes"][output["blob_id"]]["content"], large_output)
        self.assertEqual(data["tool_result_replacements"][0]["blob_id"], output["blob_id"])
        self.assertEqual(
            result.payload["result_budget"]["externalized_refs"],
            [output["blob_id"]],
        )

    def test_repo_index_still_returns_action_result_with_service_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "example.py").write_text("x = 1\n", encoding="utf-8")
            result = ActionGateway(enable_tool_execution_service=True).run(
                ActionSpec(action_id="repo-index", action_type="repo_index"),
                run_context=RunContext(run_id="run", repo_root=tmp, data={}),
            )

        self.assertEqual(result.status, "ok")
        self.assertIn("repo_intelligence", result.payload)
        self.assertEqual(result.payload["tool_execution"]["status"], "ok")

    def test_tool_execution_timeout_maps_to_action_failure(self) -> None:
        result = ActionGateway(
            command_service_factory=lambda repo_root, scopes, data: SlowCommandService(),
            enable_tool_execution_service=True,
        ).run(
            ActionSpec(
                action_id="cmd-timeout",
                action_type="run_command",
                input={"command": "slow", "timeout_seconds": 0.01},
            ),
            run_context=RunContext(run_id="run", repo_root=".", data={"preapprove_all": True}),
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "action_timeout")
        self.assertEqual(result.payload["tool_execution"]["status"], "timeout")


class FakeCommandService:
    def __init__(self, output: str) -> None:
        self.output = output

    def run_check(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "passed": True,
            "returncode": 0,
            "cwd": ".",
            "command": args[0] if args else "",
            "output": self.output,
        }


class SlowCommandService:
    def run_check(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        import time

        time.sleep(0.2)
        return {"passed": True, "output": "late"}


if __name__ == "__main__":
    unittest.main()
