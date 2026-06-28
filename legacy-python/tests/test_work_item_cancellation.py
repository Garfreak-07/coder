from __future__ import annotations

import time
import unittest

from coder_workbench.agent_graph.scheduler import ReadyWave
from coder_workbench.agent_graph.schema import ExecutionRecord, WorkItem, WorkItemOutcome
from coder_workbench.agent_graph.wave_executor import WaveExecutor, WorkItemRuntimePolicy


class WorkItemCancellationTests(unittest.TestCase):
    def test_cancelled_run_marks_work_item_cancelled(self) -> None:
        item = _item()
        control = type("RunControl", (), {"cancel_requested": True})()

        outcomes = WaveExecutor(
            lambda context: _completed(context["item"]),
            run_control=control,
        ).run_wave(_wave(item), [{"item": item, "envelope": {}}])

        self.assertEqual(outcomes[0].execution.status, "blocked")
        self.assertIn("cancelled", outcomes[0].execution.execution_summary)
        self.assertEqual(outcomes[0].execution.artifact_payload["unexpected_issues"], ["work_item_cancelled"])

    def test_timeout_produces_structured_artifact(self) -> None:
        item = _item()

        def slow(context):
            time.sleep(0.2)
            return _completed(context["item"])

        outcomes = WaveExecutor(
            slow,
            runtime_policy=WorkItemRuntimePolicy(timeout_seconds=0.01),
        ).run_wave(_wave(item), [{"item": item, "envelope": {}}])

        self.assertEqual(outcomes[0].execution.status, "blocked")
        self.assertIn("timed out", outcomes[0].execution.execution_summary)
        self.assertEqual(outcomes[0].execution.artifact_payload["unexpected_issues"], ["work_item_timeout"])


def _item() -> WorkItem:
    return WorkItem(
        work_item_id="work",
        merge_index=1,
        assignee_agent_id="executor",
        task_summary="Do work.",
    )


def _wave(item: WorkItem) -> ReadyWave:
    return ReadyWave(wave_index=1, ready_work_item_ids=[item.work_item_id], items=[item])


def _completed(item: WorkItem) -> WorkItemOutcome:
    return WorkItemOutcome(
        work_item_id=item.work_item_id,
        merge_index=item.merge_index,
        execution=ExecutionRecord(
            work_item_id=item.work_item_id,
            merge_index=item.merge_index,
            agent_id=item.assignee_agent_id,
            status="completed",
            execution_summary="done",
            execution_result_ref=f"execution_result_{item.work_item_id}",
        ),
        tests=[],
    )


if __name__ == "__main__":
    unittest.main()
