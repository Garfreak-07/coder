from __future__ import annotations

import unittest

from coder_workbench.agent_graph.cache import GraphRunCache
from coder_workbench.agent_graph.merge import build_planner_input_bundle, build_round_summary
from coder_workbench.agent_graph.schema import ExecutionRecord, PlannerOrder, TestRecord


class AgentGraphMergeTests(unittest.TestCase):
    def test_planner_input_bundle_is_compact_and_ordered_by_merge_index(self) -> None:
        cache = _cache_with_out_of_order_items()

        bundle = build_planner_input_bundle(cache)

        self.assertEqual([item.work_item_id for item in bundle.items], ["first", "second"])
        self.assertEqual([item.merge_index for item in bundle.items], [1, 2])
        self.assertEqual(bundle.plan_status, "partial_failed")
        self.assertEqual(bundle.items[0].refs, ["execution_result_first", "test_result_first"])
        self.assertEqual(bundle.items[1].test_status, "fail")
        payload = bundle.model_dump(mode="json")
        self.assertNotIn("order_index", str(payload))
        self.assertNotIn("raw", str(payload).lower())
        self.assertNotIn("full", str(payload).lower())

    def test_round_summary_is_deterministic_and_ref_only(self) -> None:
        cache = _cache_with_out_of_order_items()

        summary = build_round_summary(cache)

        self.assertEqual(summary.plan_status, "partial_failed")
        self.assertEqual(summary.completed_count, 1)
        self.assertEqual(summary.failed_count, 1)
        self.assertEqual([item.work_item_id for item in summary.ordered_state], ["first", "second"])
        self.assertEqual(summary.ordered_state[1].status, "failed_test")
        self.assertEqual(summary.ordered_state[1].refs, ["execution_result_second", "test_result_second"])


def _cache_with_out_of_order_items() -> GraphRunCache:
    planner_order = PlannerOrder.model_validate(
        {
            "round": 1,
            "round_goal": "Merge ordered results.",
            "plan_graph": {
                "work_items": [
                    {
                        "work_item_id": "second",
                        "merge_index": 2,
                        "assignee_agent_id": "executor",
                        "task_summary": "Second item.",
                        "depends_on": [],
                        "tester_agent_ids": ["tester"],
                    },
                    {
                        "work_item_id": "first",
                        "merge_index": 1,
                        "assignee_agent_id": "executor",
                        "task_summary": "First item.",
                        "depends_on": [],
                        "tester_agent_ids": ["tester"],
                    },
                ]
            },
        }
    )
    cache = GraphRunCache(round=1)
    cache.cache_planner_order(planner_order, "artifact:planner_order:round-1")
    cache.record_execution(
        ExecutionRecord(
            work_item_id="first",
            merge_index=1,
            agent_id="executor",
            status="completed",
            execution_summary="First done.",
            execution_result_ref="execution_result_first",
        )
    )
    cache.record_test(
        TestRecord(
            work_item_id="first",
            merge_index=1,
            tester_agent_id="tester",
            status="pass",
            test_summary="First test passed.",
            test_result_ref="test_result_first",
        )
    )
    cache.record_execution(
        ExecutionRecord(
            work_item_id="second",
            merge_index=2,
            agent_id="executor",
            status="completed",
            execution_summary="Second done.",
            execution_result_ref="execution_result_second",
        )
    )
    cache.record_test(
        TestRecord(
            work_item_id="second",
            merge_index=2,
            tester_agent_id="tester",
            status="fail",
            test_summary="Second test failed.",
            test_result_ref="test_result_second",
        )
    )
    return cache


if __name__ == "__main__":
    unittest.main()
