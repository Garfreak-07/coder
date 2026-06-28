from __future__ import annotations

import unittest

from coder_workbench.agent_graph.schema import AgentTaskEnvelope, WorkItem
from coder_workbench.agent_harness import CodeWorkerHarness, ExecutorSelfChecker


class ExecutorSelfCheckTests(unittest.TestCase):
    def test_executor_self_check_catches_mismatched_work_item_id(self) -> None:
        checked = ExecutorSelfChecker().check(
            {
                "artifact_type": "execution_result",
                "work_item_id": "other-work",
                "status": "completed",
                "summary": "Wrong item.",
            },
            item=_item(),
            envelope=_envelope(),
        )

        self.assertEqual(checked.status, "blocked")
        self.assertEqual(checked.artifact["status"], "blocked")
        self.assertIn("work_item_id does not match", checked.artifact["summary"])

    def test_executor_self_check_blocks_human_prompt(self) -> None:
        checked = ExecutorSelfChecker().check(
            {
                "artifact_type": "execution_result",
                "status": "completed",
                "summary": "Ask user.",
                "human_message": "Can you decide?",
            },
            item=_item(),
            envelope=_envelope(),
        )

        self.assertEqual(checked.status, "blocked")
        self.assertIn("human prompt", checked.artifact["summary"])

    def test_code_worker_self_check_fills_safe_fields(self) -> None:
        record = CodeWorkerHarness(enable_self_check=True).create_execution_result(
            item=_item(),
            envelope=_envelope(),
            coding_context_packet={"included_files": ["src/app.py"]},
        )

        self.assertEqual(record.status, "completed")
        self.assertEqual(record.artifact_payload["work_item_id"], "executor-work")
        self.assertEqual(record.artifact_payload["merge_index"], 1)
        self.assertEqual(record.artifact_payload["agent_id"], "executor")


def _item() -> WorkItem:
    return WorkItem(
        work_item_id="executor-work",
        merge_index=1,
        assignee_agent_id="executor",
        task_summary="Fix src/app.py.",
    )


def _envelope() -> AgentTaskEnvelope:
    return AgentTaskEnvelope(
        round=1,
        work_item_id="executor-work",
        merge_index=1,
        assigned_agent_id="executor",
        task_summary="Fix src/app.py.",
        planner_order_ref="planner_order_round_1",
    )


if __name__ == "__main__":
    unittest.main()
