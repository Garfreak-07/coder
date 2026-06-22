from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from coder_workbench.agent_graph.artifacts import graph_artifact_id
from coder_workbench.agent_graph.schema import ExecutionRecord, WorkItemOutcome


BuildOutcome = Callable[[dict[str, Any]], WorkItemOutcome]


class WaveExecutor:
    def __init__(self, build_work_item_outcome: BuildOutcome) -> None:
        self.build_work_item_outcome = build_work_item_outcome

    def run_wave(self, wave: Any, task_contexts: list[dict[str, Any]]) -> list[WorkItemOutcome]:
        outcomes: list[WorkItemOutcome] = []
        if not wave.items:
            return outcomes
        with ThreadPoolExecutor(max_workers=max(1, len(wave.items))) as pool:
            futures = {
                pool.submit(self.build_work_item_outcome, context): context
                for context in task_contexts
            }
            for future in as_completed(futures):
                item = futures[future]["item"]
                try:
                    outcomes.append(future.result())
                except Exception as exc:
                    outcomes.append(
                        WorkItemOutcome(
                            work_item_id=item.work_item_id,
                            merge_index=item.merge_index,
                            execution=ExecutionRecord(
                                work_item_id=item.work_item_id,
                                merge_index=item.merge_index,
                                agent_id=item.assignee_agent_id,
                                status="failed",
                                execution_summary=f"Work item failed: {exc}",
                                execution_result_ref=graph_artifact_id("execution_result", item.work_item_id),
                            ),
                            tests=[],
                        )
                    )
        return outcomes
