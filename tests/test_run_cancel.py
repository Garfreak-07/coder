from __future__ import annotations

import tempfile
import unittest

from coder_workbench.agent_graph.runner import AgentGraphRunner
from coder_workbench.core import default_planner_led_agent_workflow
from coder_workbench.runtime_kernel import RunControl


class RunCancelTests(unittest.TestCase):
    def test_cancel_requested_before_checkpoint_returns_cancelled_result(self) -> None:
        control = RunControl()
        control.request_cancel()

        with tempfile.TemporaryDirectory() as tmp:
            result = AgentGraphRunner(default_planner_led_agent_workflow()).run(
                "Cancel before running.",
                tmp,
                run_control=control,
            )

        self.assertEqual(result.status, "cancelled")
        self.assertEqual(result.status_code, "run_cancelled")
        self.assertTrue(result.data["run_control"]["cancel_requested"])


if __name__ == "__main__":
    unittest.main()
