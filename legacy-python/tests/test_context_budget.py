from __future__ import annotations

import unittest
from unittest.mock import patch

from coder_workbench.context import ContextBudget, context_compaction_enabled


class ContextBudgetTests(unittest.TestCase):
    def test_context_budget_can_be_loaded_from_run_data(self) -> None:
        budget = ContextBudget.from_data(
            {
                "context_budget": {
                    "max_input_tokens": 100,
                    "max_skill_tokens": 20,
                    "max_artifact_tokens": 30,
                    "max_tool_result_tokens": 40,
                }
            }
        )

        self.assertEqual(budget.max_input_tokens, 100)
        self.assertEqual(budget.max_skill_tokens, 20)
        self.assertEqual(budget.max_artifact_tokens, 30)
        self.assertEqual(budget.max_tool_result_tokens, 40)

    def test_context_compaction_flag_prefers_run_data_over_environment(self) -> None:
        with patch.dict("os.environ", {"CODER_ENABLE_CONTEXT_COMPACTION": "1"}):
            self.assertFalse(context_compaction_enabled({"enable_context_compaction": False}))
            self.assertTrue(context_compaction_enabled({"enable_context_compaction": True}))

    def test_context_compaction_flag_reads_environment(self) -> None:
        with patch.dict("os.environ", {"CODER_ENABLE_CONTEXT_COMPACTION": "yes"}):
            self.assertTrue(context_compaction_enabled({}))


if __name__ == "__main__":
    unittest.main()
