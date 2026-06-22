from __future__ import annotations

import unittest

from coder_workbench.agent_graph.scheduler import ReadyWave
from coder_workbench.agent_graph.schema import ExecutionRecord, WorkItem, WorkItemOutcome
from coder_workbench.agent_graph.wave_executor import WaveExecutor, WorkItemRuntimePolicy


class WorkItemRetryTests(unittest.TestCase):
    def test_retry_occurs_only_for_configured_transient_status(self) -> None:
        item = _item()
        calls = 0

        def build(context):
            nonlocal calls
            calls += 1
            if calls == 1:
                return _failed(item, "transient_model_error")
            return _completed(item)

        outcomes = WaveExecutor(
            build,
            runtime_policy=WorkItemRuntimePolicy(max_retries=1, retry_on_status_codes=["transient_model_error"]),
            enable_retry=True,
        ).run_wave(_wave(item), [{"item": item, "envelope": {}}])

        self.assertEqual(calls, 2)
        self.assertEqual(outcomes[0].execution.status, "completed")

    def test_retry_does_not_run_for_unconfigured_error(self) -> None:
        item = _item()
        calls = 0

        def build(context):
            nonlocal calls
            calls += 1
            return _failed(item, "permission_denied")

        outcomes = WaveExecutor(
            build,
            runtime_policy=WorkItemRuntimePolicy(max_retries=1, retry_on_status_codes=["transient_model_error"]),
            enable_retry=True,
        ).run_wave(_wave(item), [{"item": item, "envelope": {}}])

        self.assertEqual(calls, 1)
        self.assertEqual(outcomes[0].execution.status, "failed")


def _item() -> WorkItem:
    return WorkItem(
        work_item_id="work",
        merge_index=1,
        assignee_agent_id="executor",
        task_summary="Do work.",
    )


def _wave(item: WorkItem) -> ReadyWave:
    return ReadyWave(wave_index=1, ready_work_item_ids=[item.work_item_id], items=[item])


def _failed(item: WorkItem, error_code: str) -> WorkItemOutcome:
    return WorkItemOutcome(
        work_item_id=item.work_item_id,
        merge_index=item.merge_index,
        execution=ExecutionRecord(
            work_item_id=item.work_item_id,
            merge_index=item.merge_index,
            agent_id=item.assignee_agent_id,
            status="failed",
            execution_summary=error_code,
            execution_result_ref=f"execution_result_{item.work_item_id}",
            artifact_payload={
                "artifact_type": "execution_result",
                "status": "failed",
                "summary": error_code,
                "unexpected_issues": [error_code],
            },
        ),
        tests=[],
    )


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
