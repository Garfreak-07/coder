from __future__ import annotations

import unittest

from coder_workbench.actions import ActionResult, ActionSpec, RunContext
from coder_workbench.actions.events import action_completed_payload, action_started_payload


class ActionEventsTests(unittest.TestCase):
    def test_action_started_payload_shape(self) -> None:
        spec = ActionSpec(
            action_id="plugin:1",
            action_type="call_plugin",
            risk_level="medium",
            requires_permission=True,
        )
        payload = action_started_payload(spec, RunContext(run_id="run", repo_root="."))

        self.assertEqual(
            payload,
            {
                "action_id": "plugin:1",
                "action_type": "call_plugin",
                "risk_level": "medium",
                "requires_permission": True,
                "run_id": "run",
            },
        )

    def test_action_completed_payload_shape(self) -> None:
        spec = ActionSpec(action_id="plugin:1", action_type="call_plugin")
        result = ActionResult(
            status="blocked",
            output_ref="tool_result_round_1_1",
            summary="Needs approval.",
            error_code="plugin_requires_approval",
        )

        self.assertEqual(
            action_completed_payload(spec, result),
            {
                "action_id": "plugin:1",
                "action_type": "call_plugin",
                "status": "blocked",
                "error_code": "plugin_requires_approval",
                "output_ref": "tool_result_round_1_1",
                "summary": "Needs approval.",
            },
        )


if __name__ == "__main__":
    unittest.main()
