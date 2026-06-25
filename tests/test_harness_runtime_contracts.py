import unittest

from coder_workbench.harness_runtime import (
    CONVERSATION_HARNESS_ID,
    LEGACY_HARNESS_ALIASES,
    TASK_EXECUTION_HARNESS_ID,
    harness_contract_for_id,
    resolve_harness_id,
)


class HarnessRuntimeContractTests(unittest.TestCase):
    def test_canonical_contracts_define_conversation_and_task_execution(self) -> None:
        conversation = harness_contract_for_id(CONVERSATION_HARNESS_ID)
        task_execution = harness_contract_for_id(TASK_EXECUTION_HARNESS_ID)

        self.assertEqual(conversation.role, "planner")
        self.assertEqual(conversation.modes, ["planning_chat", "workflow_supervisor"])
        self.assertTrue(conversation.may_talk_to_user)
        self.assertFalse(conversation.may_write_files)
        self.assertFalse(conversation.may_run_commands)
        self.assertIn("planner_order", conversation.output_artifacts)
        self.assertIn("final_report", conversation.output_artifacts)

        self.assertEqual(task_execution.role, "executor")
        self.assertEqual(task_execution.modes, ["task_execution"])
        self.assertFalse(task_execution.may_talk_to_user)
        self.assertTrue(task_execution.may_write_files)
        self.assertTrue(task_execution.may_run_commands)
        self.assertIn("execution_result", task_execution.output_artifacts)

    def test_legacy_harness_aliases_resolve_to_canonical_contracts(self) -> None:
        self.assertEqual(
            LEGACY_HARNESS_ALIASES["planner-order-harness"],
            (CONVERSATION_HARNESS_ID, "workflow_supervisor"),
        )
        self.assertEqual(
            LEGACY_HARNESS_ALIASES["code-worker-harness"],
            (TASK_EXECUTION_HARNESS_ID, "task_execution"),
        )
        self.assertEqual(resolve_harness_id("final-report-harness"), (CONVERSATION_HARNESS_ID, "workflow_supervisor"))
        self.assertEqual(harness_contract_for_id("code-worker-harness").harness_id, TASK_EXECUTION_HARNESS_ID)

    def test_unknown_harness_id_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            harness_contract_for_id("unknown-harness")


if __name__ == "__main__":
    unittest.main()
