from __future__ import annotations

import unittest

from coder_workbench.agent_graph.scheduler import ReadyWave
from coder_workbench.agent_graph.schema import WorkItem
from coder_workbench.agent_graph.wave_executor import WaveExecutor


class WaveExecutorTests(unittest.TestCase):
    def test_wave_executor_converts_worker_exception_to_failed_outcome(self) -> None:
        def boom(context):
            raise RuntimeError("boom")

        item = WorkItem(
            work_item_id="work",
            merge_index=1,
            assignee_agent_id="executor",
            task_summary="Do work.",
        )
        wave = ReadyWave(wave_index=1, ready_work_item_ids=["work"], items=[item])

        outcomes = WaveExecutor(boom).run_wave(wave, [{"item": item, "envelope": {}}])

        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0].execution.status, "failed")
        self.assertIn("boom", outcomes[0].execution.execution_summary)


if __name__ == "__main__":
    unittest.main()
