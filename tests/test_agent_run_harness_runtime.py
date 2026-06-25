from __future__ import annotations

import tempfile
import unittest

from coder_workbench.agent_graph.agent_run import AgentRun
from coder_workbench.agent_graph.runner import AgentGraphRunner
from coder_workbench.agent_graph.schema import AgentTaskEnvelope, PlannerInputBundle, PlannerInputBundleItem, WorkItem
from coder_workbench.core import default_planner_led_agent_workflow


class AgentRunHarnessRuntimeTests(unittest.TestCase):
    def test_agent_run_routes_current_paths_through_harness_runtime_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = AgentGraphRunner(default_planner_led_agent_workflow()).run(
                "Route through harness runtime.",
                tmp,
                initial_data={"planner_mode": "single_executor"},
            )

        operations = [
            event.payload.get("legacy_operation")
            for event in result.events
            if event.type == "harness_runtime.fallback.legacy"
        ]

        self.assertEqual(result.status, "completed")
        self.assertIn("planner_order", operations)
        self.assertIn("planner_decision", operations)

    def test_agent_run_execution_path_uses_harness_runtime_fallback(self) -> None:
        workflow = default_planner_led_agent_workflow()
        events: list[str] = []

        def emit(event_type: str, message: str, **payload: object) -> None:
            if event_type == "harness_runtime.fallback.legacy":
                events.append(str(payload.get("legacy_operation")))

        agent_run = AgentRun(workflow, initial_data={"repo_root": "."})
        item = WorkItem(
            work_item_id="executor-work",
            merge_index=1,
            assignee_agent_id="executor",
            task_summary="Do work.",
            depends_on=[],
        )
        envelope = AgentTaskEnvelope(
            round=1,
            work_item_id=item.work_item_id,
            merge_index=item.merge_index,
            assigned_agent_id=item.assignee_agent_id,
            task_summary=item.task_summary,
            planner_order_ref="planner_order_round_1",
        )
        execution = agent_run.run_execution(item=item, envelope=envelope, emit=emit)

        self.assertEqual(execution.status, "completed")
        self.assertIn("task_execution", events)


if __name__ == "__main__":
    unittest.main()
