from __future__ import annotations

import unittest

from coder_workbench.agent_graph.cache import GraphRunCache
from coder_workbench.agent_graph.round_working_set import RoundWorkingSet
from coder_workbench.agent_graph.schema import ExecutionRecord, PlannerOrder


class RoundWorkingSetTests(unittest.TestCase):
    def test_graph_run_cache_is_compatibility_alias(self) -> None:
        cache = GraphRunCache(round=2)

        self.assertIsInstance(cache, RoundWorkingSet)
        self.assertEqual(cache.round, 2)

    def test_records_runtime_refs_without_changing_execution_refs(self) -> None:
        cache = RoundWorkingSet()
        cache.cache_planner_order(_order(), "planner_order_round_1")
        cache.record_execution(
            ExecutionRecord(
                work_item_id="executor-work",
                merge_index=1,
                agent_id="executor",
                status="completed",
                execution_summary="Done.",
                execution_result_ref="execution_result_executor-work",
            )
        )
        cache.record_context_packet_ref("executor-work", "context-ref")
        cache.record_native_runtime_ref("executor-work", "native-ref")
        cache.record_native_runtime_ref("executor-work", "native-ref")
        cache.record_diff_ref("executor-work", "diff-ref")
        cache.record_log_ref("executor-work", "log-ref")

        self.assertEqual(cache.refs_for_work_item("executor-work"), ["execution_result_executor-work"])
        self.assertEqual(cache.context_packet_refs["executor-work"], "context-ref")
        self.assertEqual(
            cache.runtime_refs_for_work_item("executor-work"),
            {
                "native_runtime_refs": ["native-ref"],
                "diff_refs": ["diff-ref"],
                "log_refs": ["log-ref"],
            },
        )

    def test_runtime_payload_exposes_refs_not_raw_events(self) -> None:
        cache = RoundWorkingSet()
        cache.record_native_runtime_ref("work", "native-event-id")

        payload = cache.as_runtime_payload()

        self.assertEqual(payload["native_runtime_refs"], {"work": ["native-event-id"]})
        self.assertNotIn("native_events", payload)


def _order() -> PlannerOrder:
    return PlannerOrder.model_validate(
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
                        "task_summary": "Do work.",
                        "depends_on": [],
                    }
                ]
            },
        }
    )


if __name__ == "__main__":
    unittest.main()
