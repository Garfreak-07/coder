from __future__ import annotations

import unittest

from coder_workbench.agent_graph.agent_run import AgentRun
from coder_workbench.agent_graph.schema import AgentTaskEnvelope, WorkItem
from coder_workbench.context import build_harness_context_packet
from coder_workbench.core import default_planner_led_agent_workflow


class HarnessContextPacketTests(unittest.TestCase):
    def test_planning_chat_packet_uses_hot_warm_cold_shape(self) -> None:
        packet = build_harness_context_packet(
            mode="planning_chat",
            user_goal="Build feature.",
            workflow_id="workflow",
            agent_id="planner",
            selected_knowledge_pack_ids=["kb"],
            selected_skill_pack_ids=["skill"],
            selected_memory_pack_ids=["memory"],
        )

        self.assertEqual(packet["schema_version"], "harness-context-packet/v1")
        self.assertEqual(packet["hot"]["user_goal"], "Build feature.")
        self.assertEqual(packet["hot"]["selected_skill_pack_ids"], ["skill"])
        self.assertEqual(packet["warm"]["workflow_summary"], {"workflow_id": "workflow"})
        self.assertNotIn("raw_events", str(packet))
        self.assertNotIn("terminal_log", str(packet))

    def test_workflow_supervisor_packet_keeps_runtime_facts_as_refs(self) -> None:
        packet = build_harness_context_packet(
            mode="workflow_supervisor",
            user_goal="Finish run.",
            workflow_id="workflow",
            agent_id="planner",
            state_view={"status": "running", "round": 1},
            capability_set={"tools": [{"name": "inspect_artifact"}], "denied": [{"name": "push"}]},
            evidence_refs=["execution-result-ref"],
            native_event_refs=["native-event-ref"],
        )

        self.assertEqual(packet["warm"]["run_state_summary"], {"status": "running", "round": 1})
        self.assertEqual(
            packet["cold_refs"],
            [
                {"ref_type": "evidence", "refs": ["execution-result-ref"]},
                {"ref_type": "native_runtime", "refs": ["native-event-ref"]},
            ],
        )

    def test_agent_run_harness_context_carries_task_execution_packet(self) -> None:
        workflow = default_planner_led_agent_workflow()
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
            planner_order_ref="planner-order-ref",
            upstream_refs=["upstream-ref"],
        )
        context = AgentRun(workflow, initial_data={"request": "Do work."})._harness_context(
            agent_id="executor",
            harness_id="task-execution-harness",
            mode="task_execution",
            profile_id="internal-fallback-task-executor",
            round_number=1,
            state_view={},
            capability_set={"tools": [{"name": "return_execution_result"}]},
            work_item=item,
            task_envelope=envelope,
        )

        packet = context.context_packet or {}
        self.assertEqual(packet["mode"], "task_execution")
        self.assertEqual(packet["hot"]["work_item"]["work_item_id"], "executor-work")
        self.assertEqual(packet["cold_refs"], [{"ref_type": "upstream", "refs": ["upstream-ref"]}, {"ref_type": "planner_order", "refs": ["planner-order-ref"]}])


if __name__ == "__main__":
    unittest.main()
