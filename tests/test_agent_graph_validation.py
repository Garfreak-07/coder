from __future__ import annotations

import unittest

from coder_workbench.agent_graph.schema import PlannerOrder
from coder_workbench.agent_graph.validation import validate_planner_order
from coder_workbench.core import AgentWorkflowSpec, default_planner_led_agent_workflow, validate_agent_workflow_payload


class AgentGraphStaticValidationTests(unittest.TestCase):
    def test_legacy_tester_workflow_is_rejected(self) -> None:
        payload = default_planner_led_agent_workflow().model_dump(mode="json", by_alias=True)
        payload["agents"].append(
            {
                "id": "legacy-review",
                "name": "Legacy Review",
                "role": "tester",
                "model_tier": "standard",
                "can_talk_to_human": False,
                "capabilities": ["model_review", "return_test_result"],
            }
        )
        payload["edges"] = [
            {"from": "planner", "to": "executor"},
            {"from": "executor", "to": "legacy-review"},
            {"from": "legacy-review", "to": "planner", "loop": True},
        ]

        result = validate_agent_workflow_payload(payload)

        self.assertEqual(result.status, "error")
        self.assertIn("invalid_agent_role", {issue.code for issue in result.issues})

    def test_workflow_with_test_result_capability_is_rejected(self) -> None:
        payload = default_planner_led_agent_workflow().model_dump(mode="json", by_alias=True)
        payload["agents"][1]["capabilities"].append("return_test_result")

        result = validate_agent_workflow_payload(payload)

        self.assertEqual(result.status, "error")
        self.assertTrue(any("return_test_result" in issue.message for issue in result.issues))

    def test_planner_order_accepts_executor_work_items(self) -> None:
        workflow = default_planner_led_agent_workflow()
        order = PlannerOrder.model_validate(
            {
                "artifact_type": "planner_order",
                "round": 1,
                "round_goal": "Implement",
                "plan_graph": {
                    "work_items": [
                        {
                            "work_item_id": "executor-work",
                            "merge_index": 1,
                            "assignee_agent_id": "executor",
                            "task_summary": "Do the work.",
                            "depends_on": [],
                        }
                    ]
                },
            }
        )

        result = validate_planner_order(workflow, order)

        self.assertEqual(result.status, "pass")

    def test_planner_order_dependency_cycle_is_rejected(self) -> None:
        workflow = default_planner_led_agent_workflow()
        order = PlannerOrder.model_validate(
            {
                "artifact_type": "planner_order",
                "round": 1,
                "round_goal": "Implement",
                "plan_graph": {
                    "work_items": [
                        {
                            "work_item_id": "a",
                            "merge_index": 1,
                            "assignee_agent_id": "executor",
                            "task_summary": "A",
                            "depends_on": ["b"],
                        },
                        {
                            "work_item_id": "b",
                            "merge_index": 2,
                            "assignee_agent_id": "executor",
                            "task_summary": "B",
                            "depends_on": ["a"],
                        },
                    ]
                },
            }
        )

        result = validate_planner_order(workflow, order)

        self.assertEqual(result.status, "error")
        self.assertIn("planner_order_dependency_cycle", {issue.code for issue in result.issues})


if __name__ == "__main__":
    unittest.main()
