from __future__ import annotations

import unittest

from coder_workbench.agent_graph.cache import GraphRunCache
from coder_workbench.agent_graph.merge import build_planner_input_bundle, build_round_summary
from coder_workbench.agent_graph.schema import ExecutionRecord, PlannerOrder


class AgentGraphMergeTests(unittest.TestCase):
    def test_planner_bundle_and_round_summary_use_execution_verification(self) -> None:
        cache = GraphRunCache()
        order = PlannerOrder.model_validate(
            {
                "artifact_type": "planner_order",
                "round": 1,
                "round_goal": "Implement",
                "plan_graph": {
                    "work_items": [
                        {
                            "work_item_id": "first",
                            "merge_index": 1,
                            "assignee_agent_id": "executor",
                            "task_summary": "First",
                            "depends_on": [],
                        },
                        {
                            "work_item_id": "second",
                            "merge_index": 2,
                            "assignee_agent_id": "executor",
                            "task_summary": "Second",
                            "depends_on": [],
                        },
                    ]
                },
            }
        )
        cache.cache_planner_order(order, "planner_order_round_1")
        cache.record_execution(_execution("first", 1, "completed", "First done.", "pass"))
        cache.record_execution(_execution("second", 2, "blocked", "Second blocked.", "blocked"))

        bundle = build_planner_input_bundle(cache)
        summary = build_round_summary(cache)

        self.assertEqual(bundle.plan_status, "blocked")
        self.assertEqual(bundle.items[0].refs, ["execution_result_first"])
        self.assertEqual(bundle.items[0].verification_status, "pass")
        self.assertEqual(bundle.items[1].verification_status, "blocked")
        self.assertEqual(summary.plan_status, "blocked")
        self.assertEqual(summary.completed_count, 1)
        self.assertEqual(summary.blocked_count, 1)
        self.assertEqual(summary.ordered_state[1].status, "blocked")


def _execution(work_item_id: str, merge_index: int, status: str, summary: str, verification_status: str) -> ExecutionRecord:
    return ExecutionRecord(
        work_item_id=work_item_id,
        merge_index=merge_index,
        agent_id="executor",
        status=status,
        execution_summary=summary,
        execution_result_ref=f"execution_result_{work_item_id}",
        artifact_payload={
            "artifact_type": "execution_result",
            "round": 1,
            "work_item_id": work_item_id,
            "merge_index": merge_index,
            "agent_id": "executor",
            "status": status,
            "summary": summary,
            "outputs": [f"execution_result_{work_item_id}"] if status == "completed" else [],
            "unexpected_issues": [] if status == "completed" else ["verification_failed"],
            "remaining_work": [] if status == "completed" else [summary],
            "blocker_type": None if status == "completed" else "verification_failed",
            "verification": {
                "status": verification_status,
                "checks_run": [
                    {
                        "check_id": "static",
                        "kind": "static",
                        "command": None,
                        "status": verification_status,
                        "summary": summary,
                        "output_ref": None,
                        "evidence_refs": [f"execution_result_{work_item_id}"],
                    }
                ],
                "evidence_refs": [f"execution_result_{work_item_id}"],
                "confidence": "medium",
                "remaining_work": [] if verification_status == "pass" else [summary],
                "no_check_rationale": None,
                "repair_attempted": False,
                "repair_summary": None,
            },
        },
    )


if __name__ == "__main__":
    unittest.main()
