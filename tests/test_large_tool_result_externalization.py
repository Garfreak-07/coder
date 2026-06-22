from __future__ import annotations

import unittest
from typing import Any

from coder_workbench.actions import ActionGateway, ActionSpec, ResultBudget, RunContext


class LargeToolResultExternalizationTests(unittest.TestCase):
    def test_full_tool_result_ref_can_be_retrieved_from_run_data(self) -> None:
        data: dict[str, Any] = {"preapprove_all": True}
        large_output = "line\n" * 1000
        result = ActionGateway(
            command_service_factory=lambda repo_root, scopes, data: FakeCommandService(large_output),
            enable_tool_execution_service=True,
            result_budget=ResultBudget(max_inline_chars=100, preview_chars=20),
        ).run(
            ActionSpec(action_id="cmd", action_type="run_command", input={"command": "fake"}),
            run_context=RunContext(run_id="run", repo_root=".", data=data),
        )

        full_ref = result.payload["result"]["output"]["full_result_ref"]

        self.assertEqual(result.status, "ok")
        self.assertEqual(data["tool_result_store"][full_ref]["content"], large_output)
        self.assertEqual(data["tool_result_store"][full_ref]["original_chars"], len(large_output))


class FakeCommandService:
    def __init__(self, output: str) -> None:
        self.output = output

    def run_check(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"passed": True, "output": self.output}


if __name__ == "__main__":
    unittest.main()
