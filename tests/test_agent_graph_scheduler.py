from __future__ import annotations

import tempfile
import unittest

from coder_workbench.agent_graph.runner import AgentGraphRunner
from coder_workbench.agent_graph.scheduler import AgentGraphScheduler
from coder_workbench.agent_graph.schema import WorkItem
from coder_workbench.core import default_planner_led_agent_workflow


def item(
    work_item_id: str,
    merge_index: int,
    depends_on: list[str] | None = None,
) -> WorkItem:
    return WorkItem(
        work_item_id=work_item_id,
        merge_index=merge_index,
        assignee_agent_id=f"{work_item_id}-agent",
        task_summary=f"Task {work_item_id}",
        depends_on=depends_on or [],
        tester_agent_ids=[],
    )


class AgentGraphSchedulerTests(unittest.TestCase):
    def test_depends_on_waits_for_all_upstreams(self) -> None:
        scheduler = AgentGraphScheduler(
            [
                item("a", 1),
                item("b", 2, ["a", "c"]),
                item("c", 3),
            ],
            max_concurrency=3,
        )

        self.assertEqual([ready.work_item_id for ready in scheduler.ready_items()], ["a", "c"])
        scheduler.mark_completed("a")
        self.assertEqual([ready.work_item_id for ready in scheduler.ready_items()], ["c"])
        scheduler.mark_completed("c")
        self.assertEqual([ready.work_item_id for ready in scheduler.ready_items()], ["b"])

    def test_merge_index_does_not_make_independent_items_wait(self) -> None:
        scheduler = AgentGraphScheduler(
            [
                item("b", 2),
                item("a", 1),
                item("c", 3, ["a"]),
            ],
            max_concurrency=3,
        )

        self.assertCountEqual([ready.work_item_id for ready in scheduler.ready_items()], ["a", "b"])

    def test_next_wave_splits_ready_from_resource_deferred_items(self) -> None:
        scheduler = AgentGraphScheduler(
            [
                item("a", 1),
                item("b", 2),
                item("c", 3),
                item("d", 4, ["a"]),
            ],
            max_concurrency=2,
        )

        wave = scheduler.next_wave()

        self.assertEqual(wave.wave_index, 1)
        self.assertEqual(wave.ready_work_item_ids, ["a", "b", "c"])
        self.assertEqual([ready.work_item_id for ready in wave.items], ["a", "b"])
        self.assertEqual(wave.deferred_ready_work_item_ids, ["c"])
        self.assertEqual([item.work_item_id for item in scheduler.resource_deferred_items()], ["c"])
        self.assertEqual([item.work_item_id for item in scheduler.dependency_waiting_items()], ["d"])

    def test_wave_index_advances_only_when_items_dispatch(self) -> None:
        scheduler = AgentGraphScheduler([item("b", 2, ["a"])], max_concurrency=2)

        empty_wave = scheduler.next_wave()

        self.assertEqual(empty_wave.wave_index, 1)
        self.assertEqual(empty_wave.items, [])
        self.assertEqual(scheduler.next_wave().wave_index, 1)

    def test_failed_upstream_blocks_downstream(self) -> None:
        scheduler = AgentGraphScheduler([item("a", 1), item("b", 2, ["a"])])

        scheduler.mark_failed("a")
        blocked = scheduler.block_items_with_failed_upstreams()

        self.assertEqual([record.work_item.work_item_id for record in blocked], ["b"])
        self.assertEqual(blocked[0].blocked_by, ["a"])
        self.assertEqual(scheduler.status_by_id["b"], "blocked")


class AgentGraphRunnerSchedulerTests(unittest.TestCase):
    def test_runner_waits_for_dependency_and_passes_upstream_refs(self) -> None:
        planner_order = {
            "artifact_type": "planner_order",
            "round": 1,
            "round_goal": "Run ordered work.",
            "plan_graph": {
                "work_items": [
                    {
                        "work_item_id": "first",
                        "merge_index": 1,
                        "assignee_agent_id": "executor",
                        "task_summary": "Run first.",
                        "depends_on": [],
                        "tester_agent_ids": ["tester"],
                    },
                    {
                        "work_item_id": "second",
                        "merge_index": 2,
                        "assignee_agent_id": "executor",
                        "task_summary": "Run second.",
                        "depends_on": ["first"],
                        "tester_agent_ids": ["tester"],
                    },
                    {
                        "work_item_id": "third",
                        "merge_index": 3,
                        "assignee_agent_id": "executor",
                        "task_summary": "Run third.",
                        "depends_on": [],
                        "tester_agent_ids": [],
                    },
                ]
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            result = AgentGraphRunner(default_planner_led_agent_workflow()).run(
                "Run ordered work.",
                tmp,
                initial_data={"planner_order": planner_order, "max_concurrency": 2},
            )

        self.assertEqual(result.status, "completed")
        self.assertEqual(
            result.data["scheduler_status"],
            {"first": "completed", "second": "completed", "third": "completed"},
        )
        events = [event.type for event in result.events]
        self.assertIn("join.completed", events)
        first_completed = next(
            index
            for index, event in enumerate(result.events)
            if event.type == "agent_task.completed" and event.payload["work_item_id"] == "first"
        )
        second_started = next(
            index
            for index, event in enumerate(result.events)
            if event.type == "agent_task.started" and event.payload["work_item_id"] == "second"
        )
        self.assertGreater(second_started, first_completed)
        second_task = result.data["graph_run_cache"]["agent_tasks"]["second"]
        self.assertEqual(
            second_task["upstream_refs"],
            ["execution_result_first", "test_result_first_tester"],
        )

    def test_runner_emits_waves_and_resource_deferred_events(self) -> None:
        planner_order = {
            "artifact_type": "planner_order",
            "round": 1,
            "round_goal": "Run bounded ready work.",
            "plan_graph": {
                "work_items": [
                    {
                        "work_item_id": "a",
                        "merge_index": 1,
                        "assignee_agent_id": "executor",
                        "task_summary": "Run A.",
                        "depends_on": [],
                        "tester_agent_ids": [],
                    },
                    {
                        "work_item_id": "b",
                        "merge_index": 2,
                        "assignee_agent_id": "executor",
                        "task_summary": "Run B.",
                        "depends_on": [],
                        "tester_agent_ids": [],
                    },
                    {
                        "work_item_id": "c",
                        "merge_index": 3,
                        "assignee_agent_id": "executor",
                        "task_summary": "Run C.",
                        "depends_on": [],
                        "tester_agent_ids": [],
                    },
                ]
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            result = AgentGraphRunner(default_planner_led_agent_workflow()).run(
                "Run bounded ready work.",
                tmp,
                initial_data={"planner_order": planner_order, "max_concurrency": 2},
            )

        self.assertEqual(result.status, "completed")
        wave_events = [event for event in result.events if event.type == "agent_graph.wave.started"]
        self.assertEqual([event.payload["wave_index"] for event in wave_events], [1, 2])
        self.assertEqual(wave_events[0].payload["ready_work_item_ids"], ["a", "b", "c"])
        self.assertEqual(wave_events[0].payload["work_item_ids"], ["a", "b"])
        self.assertEqual(wave_events[0].payload["deferred_ready_work_item_ids"], ["c"])
        deferred = [event for event in result.events if event.type == "resource.deferred"]
        self.assertEqual(deferred[0].payload["deferred_work_item_ids"], ["c"])

    def test_runner_merge_order_is_not_dispatch_order(self) -> None:
        planner_order = {
            "artifact_type": "planner_order",
            "round": 1,
            "round_goal": "Separate dispatch from merge.",
            "plan_graph": {
                "work_items": [
                    {
                        "work_item_id": "z-work",
                        "merge_index": 1,
                        "assignee_agent_id": "executor",
                        "task_summary": "Merge first.",
                        "depends_on": [],
                        "tester_agent_ids": [],
                    },
                    {
                        "work_item_id": "a-work",
                        "merge_index": 2,
                        "assignee_agent_id": "executor",
                        "task_summary": "Merge second.",
                        "depends_on": [],
                        "tester_agent_ids": [],
                    },
                ]
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            result = AgentGraphRunner(default_planner_led_agent_workflow()).run(
                "Separate dispatch from merge.",
                tmp,
                initial_data={"planner_order": planner_order, "max_concurrency": 2},
            )

        self.assertEqual(result.status, "completed")
        wave_started = next(event for event in result.events if event.type == "agent_graph.wave.started")
        self.assertEqual(wave_started.payload["work_item_ids"], ["a-work", "z-work"])
        self.assertEqual(
            [item["work_item_id"] for item in result.data["planner_input_bundle"]["items"]],
            ["z-work", "a-work"],
        )


if __name__ == "__main__":
    unittest.main()
