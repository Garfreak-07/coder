from __future__ import annotations

import tempfile
import unittest

from coder_workbench.agent_graph.cache import GraphRunCache
from coder_workbench.agent_graph.runner import AgentGraphRunner
from coder_workbench.agent_graph.schema import ExecutionRecord, PlannerOrder, WorkItem
from coder_workbench.core import default_planner_led_agent_workflow


class AgentGraphPhase2Tests(unittest.TestCase):
    def test_graph_run_cache_records_execution_refs_only(self) -> None:
        cache = GraphRunCache()
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
                            "task_summary": "Do work.",
                            "depends_on": [],
                        }
                    ]
                },
            }
        )

        cache.cache_planner_order(order, "planner_order_round_1")
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

        self.assertEqual(cache.refs_for_work_item("executor-work"), ["execution_result_executor-work"])
        self.assertNotIn("test_cache", cache.model_dump(mode="json"))

    def test_runner_records_execution_verification_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = AgentGraphRunner(default_planner_led_agent_workflow()).run("Implement.", tmp)

        self.assertEqual(result.status, "completed")
        execution_artifacts = [
            artifact
            for artifact in result.artifacts.values()
            if isinstance(artifact, dict) and artifact.get("artifact_type") == "execution_result"
        ]
        self.assertEqual(len(execution_artifacts), 1)
        self.assertIn(execution_artifacts[0]["verification"]["status"], {"pass", "skipped"})
        self.assertNotIn("test_cache", result.data.get("graph_run_cache", {}))

    def test_work_item_schema_has_no_legacy_review_fields(self) -> None:
        self.assertNotIn("tester_agent_ids", WorkItem.model_fields)


if __name__ == "__main__":
    unittest.main()
