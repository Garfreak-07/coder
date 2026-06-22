from __future__ import annotations

import tempfile
import unittest

from coder_workbench.agent_engine import TesterEngine, default_agent_engine_registry
from coder_workbench.agent_graph.runner import AgentGraphRunner
from coder_workbench.agent_graph import schema
from coder_workbench.agent_graph.schema import WorkItem
from coder_workbench.core import AgentWorkflowSpec


class TesterAggregationWithoutFinalEngineTests(unittest.TestCase):
    def test_tester_engine_aggregates_upstream_test_evidence(self) -> None:
        registry = default_agent_engine_registry()
        item = WorkItem(
            work_item_id="executor-work",
            merge_index=1,
            assignee_agent_id="executor",
            task_summary="Implement requested change.",
            tester_agent_ids=["tester-aggregate"],
        )
        execution_artifact = {
            "artifact_id": "execution_result_executor-work_executor",
            "artifact_type": "execution_result",
            "round": 1,
            "work_item_id": "executor-work",
            "merge_index": 1,
            "agent_id": "executor",
            "status": "completed",
            "summary": "Executor completed the requested change.",
        }
        upstream_artifacts = [
            {
                "artifact_id": "test_result_executor-work_tester-a",
                "artifact_type": "test_result",
                "round": 1,
                "work_item_id": "executor-work",
                "tester_agent_id": "tester-a",
                "status": "pass",
                "summary": "Tester A passed.",
            },
            {
                "artifact_id": "test_result_executor-work_tester-b",
                "artifact_type": "test_result",
                "round": 1,
                "work_item_id": "executor-work",
                "tester_agent_id": "tester-b",
                "status": "pass",
                "summary": "Tester B passed.",
            },
        ]

        record = registry.tester().run_test(
            agent_workflow=_workflow_with_aggregate_tester(),
            item=item,
            execution_artifact=execution_artifact,
            upstream_artifacts=upstream_artifacts,
            tester_agent_id="tester-aggregate",
        )

        self.assertIsInstance(registry.get("tester-engine"), TesterEngine)
        self.assertEqual(record.artifact_payload["artifact_type"], "test_result")
        self.assertEqual(record.artifact_payload["tester_agent_id"], "tester-aggregate")
        self.assertEqual(record.status, "pass")
        self.assertEqual(record.test_result_ref, "test_result_executor-work_tester-aggregate")
        self.assertEqual(
            record.artifact_payload["evidence"],
            [
                "execution_result_executor-work_executor",
                "test_result_executor-work_tester-a",
                "test_result_executor-work_tester-b",
            ],
        )

    def test_no_final_engine_or_final_test_schema_exists(self) -> None:
        registry = default_agent_engine_registry()

        self.assertEqual(registry.ids(), ["code-worker-engine", "planner-engine", "tester-engine"])
        self.assertFalse(hasattr(schema, "FinalTestRecord"))
        self.assertNotIn("final_tester_agent_id", WorkItem.model_fields)

    def test_runner_uses_later_tester_to_aggregate_prior_tester_outputs(self) -> None:
        planner_order = {
            "artifact_type": "planner_order",
            "round": 1,
            "round_goal": "Collect and aggregate test evidence.",
            "plan_graph": {
                "work_items": [
                    {
                        "work_item_id": "executor-work",
                        "merge_index": 1,
                        "assignee_agent_id": "executor",
                        "task_summary": "Implement requested change.",
                        "depends_on": [],
                        "tester_agent_ids": ["tester-a", "tester-b", "tester-aggregate"],
                    }
                ]
            },
        }

        with tempfile.TemporaryDirectory() as tmp:
            result = AgentGraphRunner(_workflow_with_aggregate_tester()).run(
                "Collect and aggregate test evidence.",
                tmp,
                initial_data={"planner_order": planner_order},
            )

        self.assertEqual(result.status, "completed")
        test_records = result.data["graph_run_cache"]["test_cache"]["executor-work"]
        self.assertEqual(
            [record["tester_agent_id"] for record in test_records],
            ["tester-a", "tester-b", "tester-aggregate"],
        )
        aggregate_payload = test_records[-1]["artifact_payload"]
        self.assertEqual(aggregate_payload["artifact_type"], "test_result")
        self.assertEqual(
            aggregate_payload["evidence"],
            [
                "execution_result_executor-work",
                "test_result_executor-work_tester-a",
                "test_result_executor-work_tester-b",
            ],
        )
        self.assertNotIn("final_test_cache", result.data["graph_run_cache"])


def _workflow_with_aggregate_tester() -> AgentWorkflowSpec:
    return AgentWorkflowSpec.model_validate(
        {
            "id": "tester-aggregation",
            "version": "0.4",
            "name": "Tester Aggregation",
            "primary_planner_id": "planner",
            "agents": [
                {
                    "id": "planner",
                    "name": "Planner",
                    "role": "planner",
                    "model_tier": "best",
                    "can_talk_to_human": True,
                    "capabilities": ["negotiate_contract", "make_plan", "judge_completion"],
                },
                {
                    "id": "executor",
                    "name": "Executor",
                    "role": "executor",
                    "role_card": "executor",
                    "model_tier": "standard",
                    "can_talk_to_human": False,
                    "capabilities": ["follow_planner_order", "return_execution_result"],
                },
                {
                    "id": "tester-a",
                    "name": "Tester A",
                    "role": "tester",
                    "role_card": "tester",
                    "model_tier": "standard",
                    "can_talk_to_human": False,
                    "capabilities": ["model_review", "return_test_result"],
                },
                {
                    "id": "tester-b",
                    "name": "Tester B",
                    "role": "tester",
                    "role_card": "tester",
                    "model_tier": "standard",
                    "can_talk_to_human": False,
                    "capabilities": ["model_review", "return_test_result"],
                },
                {
                    "id": "tester-aggregate",
                    "name": "Tester Aggregate",
                    "role": "tester",
                    "role_card": "tester",
                    "model_tier": "standard",
                    "can_talk_to_human": False,
                    "capabilities": ["model_review", "return_test_result"],
                },
            ],
            "edges": [
                {"from": "planner", "to": "executor"},
                {"from": "executor", "to": "tester-a"},
                {"from": "executor", "to": "tester-b"},
                {"from": "executor", "to": "tester-aggregate"},
                {"from": "tester-a", "to": "planner", "loop": True},
                {"from": "tester-b", "to": "planner", "loop": True},
                {"from": "tester-aggregate", "to": "planner", "loop": True},
            ],
            "loop_policy": {"max_auto_rounds": 3, "user_can_change": True},
        }
    )


if __name__ == "__main__":
    unittest.main()
