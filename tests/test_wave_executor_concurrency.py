from __future__ import annotations

import threading
import time
import unittest

from coder_workbench.agent_graph.scheduler import ReadyWave
from coder_workbench.agent_graph.schema import ExecutionRecord, WorkItem, WorkItemOutcome
from coder_workbench.agent_graph.wave_executor import PartialWorkItemError, WaveExecutor, WorkItemRuntimePolicy


class WaveExecutorConcurrencyTests(unittest.TestCase):
    def test_independent_work_items_run_concurrently(self) -> None:
        items = [_item("work-a", 1), _item("work-b", 2)]
        wave = ReadyWave(wave_index=1, ready_work_item_ids=[item.work_item_id for item in items], items=items)

        def build(context):
            time.sleep(0.15)
            return _completed(context["item"])

        started = time.monotonic()
        outcomes = WaveExecutor(build).run_wave(wave, [{"item": item, "envelope": {}} for item in items])
        elapsed = time.monotonic() - started

        self.assertEqual({outcome.work_item_id for outcome in outcomes}, {"work-a", "work-b"})
        self.assertLess(elapsed, 0.28)

    def test_partial_result_is_recorded_when_allowed(self) -> None:
        item = _item("work", 1)
        partial = _blocked(item, "Partial evidence recorded.", "partial_evidence")

        def build(context):
            raise PartialWorkItemError("failed after partial", partial_outcome=partial)

        outcomes = WaveExecutor(
            build,
            runtime_policy=WorkItemRuntimePolicy(allow_partial_result=True),
        ).run_wave(_wave(item), [{"item": item, "envelope": {}}])

        self.assertEqual(outcomes[0].execution.status, "blocked")
        self.assertEqual(outcomes[0].execution.execution_summary, "Partial evidence recorded.")

    def test_wave_diagnostics_summarize_attempts(self) -> None:
        events: list[str] = []
        item = _item("work", 1)

        def emit(event_type: str, message: str, **payload):
            events.append(event_type)

        executor = WaveExecutor(lambda context: _completed(context["item"]), emit=emit)
        executor.run_wave(_wave(item), [{"item": item, "envelope": {}}])

        self.assertEqual(executor.last_diagnostics["completed"], 1)
        self.assertIn("agent_graph.wave.diagnostics", events)


def _item(work_item_id: str, merge_index: int) -> WorkItem:
    return WorkItem(
        work_item_id=work_item_id,
        merge_index=merge_index,
        assignee_agent_id="executor",
        task_summary="Do work.",
    )


def _wave(*items: WorkItem) -> ReadyWave:
    return ReadyWave(wave_index=1, ready_work_item_ids=[item.work_item_id for item in items], items=list(items))


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


def _blocked(item: WorkItem, summary: str, error_code: str) -> WorkItemOutcome:
    return WorkItemOutcome(
        work_item_id=item.work_item_id,
        merge_index=item.merge_index,
        execution=ExecutionRecord(
            work_item_id=item.work_item_id,
            merge_index=item.merge_index,
            agent_id=item.assignee_agent_id,
            status="blocked",
            execution_summary=summary,
            execution_result_ref=f"execution_result_{item.work_item_id}",
            artifact_payload={"unexpected_issues": [error_code], "status": "blocked", "summary": summary},
        ),
        tests=[],
    )


if __name__ == "__main__":
    unittest.main()
