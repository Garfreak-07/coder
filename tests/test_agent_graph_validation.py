from __future__ import annotations

import unittest

from coder_workbench.agent_graph.schema import PlannerOrder
from coder_workbench.agent_graph.validation import validate_planner_order
from coder_workbench.core import AgentWorkflowSpec, default_planner_led_agent_workflow, validate_agent_workflow_payload


class AgentGraphStaticValidationTests(unittest.TestCase):
    def test_multiple_testers_are_valid_without_aggregate_agent(self) -> None:
        payload = default_planner_led_agent_workflow().model_dump(mode="json", by_alias=True)
        payload["agents"].append(
            {
                "id": "tester2",
                "name": "Second Tester",
                "role": "tester",
                "model_tier": "standard",
                "can_talk_to_human": False,
                "capabilities": ["model_review", "return_test_result"],
            }
        )
        payload["edges"].extend(
            [
                {"from": "executor", "to": "tester2"},
                {"from": "tester2", "to": "planner", "loop": True},
            ]
        )

        validation = validate_agent_workflow_payload(payload)

        self.assertEqual(validation.status, "pass")

    def test_worker_tester_cycle_without_planner_is_rejected(self) -> None:
        payload = default_planner_led_agent_workflow().model_dump(mode="json", by_alias=True)
        payload["edges"].append({"from": "tester", "to": "executor"})

        validation = validate_agent_workflow_payload(payload)

        self.assertEqual(validation.status, "error")
        self.assertIn("agent_cycle_without_planner", {issue.code for issue in validation.issues})


class AgentGraphPlannerOrderValidationTests(unittest.TestCase):
    def test_planner_order_cannot_assign_to_unreachable_agent(self) -> None:
        payload = default_planner_led_agent_workflow().model_dump(mode="json", by_alias=True)
        payload["agents"].append(
            {
                "id": "isolated",
                "name": "Isolated Executor",
                "role": "executor",
                "model_tier": "standard",
                "can_talk_to_human": False,
                "capabilities": ["follow_planner_order", "return_execution_result"],
            }
        )
        workflow = AgentWorkflowSpec.model_validate(payload)
        planner_order = PlannerOrder.model_validate(
            {
                "round": 1,
                "round_goal": "Try unreachable assignment.",
                "plan_graph": {
                    "work_items": [
                        {
                            "work_item_id": "isolated-work",
                            "merge_index": 1,
                            "assignee_agent_id": "isolated",
                            "task_summary": "Should not run.",
                            "depends_on": [],
                            "tester_agent_ids": [],
                        }
                    ]
                },
            }
        )

        validation = validate_planner_order(workflow, planner_order)

        self.assertEqual(validation.status, "error")
        self.assertIn("planner_order_assignee_not_reachable", {issue.code for issue in validation.issues})

    def test_planner_order_allows_multiple_testers_on_work_item(self) -> None:
        workflow = AgentWorkflowSpec.model_validate(_workflow_with_two_testers())
        planner_order = PlannerOrder.model_validate(
            {
                "round": 1,
                "round_goal": "Test in parallel.",
                "plan_graph": {
                    "work_items": [
                        {
                            "work_item_id": "executor-work",
                            "merge_index": 1,
                            "assignee_agent_id": "executor",
                            "task_summary": "Run work.",
                            "depends_on": [],
                            "tester_agent_ids": ["tester", "tester2"],
                        }
                    ]
                },
            }
        )

        validation = validate_planner_order(workflow, planner_order)

        self.assertEqual(validation.status, "pass")

    def test_planner_order_rejects_duplicate_merge_index(self) -> None:
        workflow = default_planner_led_agent_workflow()
        planner_order = PlannerOrder.model_validate(
            {
                "round": 1,
                "round_goal": "Merge deterministically.",
                "plan_graph": {
                    "work_items": [
                        {
                            "work_item_id": "first",
                            "merge_index": 1,
                            "assignee_agent_id": "executor",
                            "task_summary": "Run first.",
                            "depends_on": [],
                            "tester_agent_ids": [],
                        },
                        {
                            "work_item_id": "second",
                            "merge_index": 1,
                            "assignee_agent_id": "executor",
                            "task_summary": "Run second.",
                            "depends_on": [],
                            "tester_agent_ids": [],
                        },
                    ]
                },
            }
        )

        validation = validate_planner_order(workflow, planner_order)

        self.assertEqual(validation.status, "error")
        self.assertIn("duplicate_merge_index", {issue.code for issue in validation.issues})

    def test_planner_order_depends_on_must_be_dag(self) -> None:
        workflow = default_planner_led_agent_workflow()
        planner_order = PlannerOrder.model_validate(
            {
                "round": 1,
                "round_goal": "Reject dependency cycles.",
                "plan_graph": {
                    "work_items": [
                        {
                            "work_item_id": "a",
                            "merge_index": 1,
                            "assignee_agent_id": "executor",
                            "task_summary": "Run A.",
                            "depends_on": ["b"],
                            "tester_agent_ids": [],
                        },
                        {
                            "work_item_id": "b",
                            "merge_index": 2,
                            "assignee_agent_id": "executor",
                            "task_summary": "Run B.",
                            "depends_on": ["a"],
                            "tester_agent_ids": [],
                        },
                    ]
                },
            }
        )

        validation = validate_planner_order(workflow, planner_order)

        self.assertEqual(validation.status, "error")
        self.assertIn("planner_order_dependency_cycle", {issue.code for issue in validation.issues})


def _workflow_with_two_testers() -> dict:
    payload = default_planner_led_agent_workflow().model_dump(mode="json", by_alias=True)
    payload["agents"].append(
        {
            "id": "tester2",
            "name": "Second Tester",
            "role": "tester",
            "model_tier": "standard",
            "can_talk_to_human": False,
            "capabilities": ["model_review", "return_test_result"],
        }
    )
    payload["edges"] = [
        {"from": "planner", "to": "executor"},
        {"from": "executor", "to": "tester"},
        {"from": "executor", "to": "tester2"},
        {"from": "tester", "to": "planner", "loop": True},
        {"from": "tester2", "to": "planner", "loop": True},
    ]
    return payload


if __name__ == "__main__":
    unittest.main()
