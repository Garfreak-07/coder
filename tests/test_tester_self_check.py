from __future__ import annotations

import unittest

from coder_workbench.agent_graph.schema import WorkItem
from coder_workbench.agent_harness import TestHarness, TesterSelfChecker


class TesterSelfCheckTests(unittest.TestCase):
    def test_tester_self_check_catches_missing_evidence(self) -> None:
        checked = TesterSelfChecker().check(
            {
                "artifact_type": "test_result",
                "status": "pass",
                "summary": "Looks fine.",
                "confidence": "medium",
            },
            item=_item(),
            tester_agent_id="tester",
            evidence_refs=["execution_result_executor-work"],
            round_number=1,
        )

        self.assertEqual(checked.status, "blocked")
        self.assertEqual(checked.artifact["status"], "blocked")
        self.assertIn("evidence", checked.artifact["summary"])

    def test_tester_self_check_blocks_human_prompt(self) -> None:
        checked = TesterSelfChecker().check(
            {
                "artifact_type": "test_result",
                "status": "pass",
                "summary": "Ask user.",
                "confidence": "medium",
                "evidence": ["execution_result_executor-work"],
                "ask_human": True,
            },
            item=_item(),
            tester_agent_id="tester",
            evidence_refs=["execution_result_executor-work"],
            round_number=1,
        )

        self.assertEqual(checked.status, "blocked")
        self.assertIn("human prompt", checked.artifact["summary"])

    def test_test_harness_self_check_keeps_valid_artifact(self) -> None:
        record = TestHarness(enable_self_check=True).create_test_result(
            repo_root=".",
            item=_item(),
            tester_agent_id="tester",
            execution_artifact={
                "artifact_id": "execution_result_executor-work",
                "artifact_type": "execution_result",
                "round": 1,
                "status": "completed",
                "summary": "Done.",
            },
        )

        self.assertEqual(record.status, "pass")
        self.assertEqual(record.artifact_payload["work_item_id"], "executor-work")
        self.assertEqual(record.artifact_payload["tester_agent_id"], "tester")


def _item() -> WorkItem:
    return WorkItem(
        work_item_id="executor-work",
        merge_index=1,
        assignee_agent_id="executor",
        task_summary="Fix src/app.py.",
        tester_agent_ids=["tester"],
    )


if __name__ == "__main__":
    unittest.main()
