from __future__ import annotations

import unittest

from coder_workbench.agent_graph.schema import PlannerOrder
from coder_workbench.budget import BudgetBroker, BudgetLimit


class BudgetBrokerTests(unittest.TestCase):
    def test_reserve_within_budget_succeeds(self) -> None:
        broker = BudgetBroker(BudgetLimit(max_estimated_tokens=100, max_model_calls=1))

        reservation = broker.reserve_model_call(run_id="run", agent_id="planner", estimated_tokens=50)

        self.assertTrue(reservation.approved)
        self.assertEqual(broker.usage("run").estimated_tokens_reserved, 50)
        self.assertEqual(broker.usage("run").model_calls_reserved, 1)

    def test_reserve_over_total_budget_is_denied(self) -> None:
        broker = BudgetBroker(BudgetLimit(max_estimated_tokens=10))

        reservation = broker.reserve_context(run_id="run", estimated_tokens=20)

        self.assertFalse(reservation.approved)
        self.assertEqual(reservation.reason, "estimated_token_budget_exceeded")

    def test_reserve_over_context_call_budget_is_denied(self) -> None:
        broker = BudgetBroker(BudgetLimit(max_estimated_tokens=100, max_context_tokens_per_call=10))

        reservation = broker.reserve_context(run_id="run", estimated_tokens=20)

        self.assertFalse(reservation.approved)
        self.assertEqual(reservation.reason, "context_budget_exceeded")

    def test_commit_updates_actual_usage(self) -> None:
        broker = BudgetBroker(BudgetLimit(max_estimated_tokens=100, max_tool_calls=2))
        reservation = broker.reserve_tool_call(run_id="run", action_type="run_command", estimated_tokens=5)

        committed = broker.commit(reservation.reservation_id, actual_tokens=3)

        self.assertTrue(committed.committed)
        self.assertEqual(broker.usage("run").actual_tokens_committed, 3)
        self.assertEqual(broker.usage("run").tool_calls_committed, 1)

    def test_diagnostics_groups_reservations_by_state(self) -> None:
        broker = BudgetBroker(BudgetLimit(max_estimated_tokens=10, max_model_calls=1))
        approved = broker.reserve_model_call(run_id="run", agent_id="planner", estimated_tokens=5)
        denied = broker.reserve_model_call(run_id="run", agent_id="planner", estimated_tokens=1)

        broker.commit(approved.reservation_id, actual_tokens=4)
        diagnostics = broker.diagnostics("run")

        self.assertEqual(diagnostics["usage"]["actual_tokens_committed"], 4)
        self.assertEqual(len(diagnostics["reservations"]), 2)
        self.assertEqual(diagnostics["committed"][0]["reservation_id"], approved.reservation_id)
        self.assertEqual(diagnostics["denied"][0]["reservation_id"], denied.reservation_id)
        self.assertEqual(diagnostics["denied"][0]["reason"], "model_call_budget_exceeded")

    def test_remaining_reports_capacity_without_reserving(self) -> None:
        broker = BudgetBroker(BudgetLimit(max_estimated_tokens=100, max_model_calls=3, max_tool_calls=4))
        broker.reserve_model_call(run_id="run", agent_id="planner", estimated_tokens=25)
        broker.reserve_tool_call(run_id="run", action_type="run_command", estimated_tool_calls=2)

        remaining = broker.remaining("run")

        self.assertEqual(remaining.estimated_tokens, 75)
        self.assertEqual(remaining.model_calls, 2)
        self.assertEqual(remaining.tool_calls, 2)

    def test_round_preflight_denies_without_consuming_budget(self) -> None:
        broker = BudgetBroker(BudgetLimit(max_model_calls=1))
        broker.reserve_model_call(run_id="run", agent_id="planner")

        report = broker.preflight_round(
            run_id="run",
            planner_order=_planner_order(),
            estimated_model_calls=1,
        )

        self.assertFalse(report.approved)
        self.assertEqual(report.reason, "round_model_call_budget_exceeded")
        self.assertEqual(broker.usage("run").model_calls_reserved, 1)
        self.assertEqual(broker.reservations("run")[0]["approved"], True)

    def test_round_preflight_can_deny_context_and_tool_budgets(self) -> None:
        context_broker = BudgetBroker(BudgetLimit(max_estimated_tokens=5, max_tool_calls=1))
        context_report = context_broker.preflight_round(
            run_id="run",
            planner_order=_planner_order(),
            estimated_context_tokens_per_call=10,
        )
        tool_broker = BudgetBroker(BudgetLimit(max_tool_calls=0))
        tool_report = tool_broker.preflight_round(
            run_id="run",
            planner_order=_planner_order(),
            estimated_tool_calls=1,
        )

        self.assertEqual(context_report.reason, "round_context_budget_exceeded")
        self.assertEqual(tool_report.reason, "round_tool_call_budget_exceeded")


def _planner_order() -> PlannerOrder:
    return PlannerOrder.model_validate(
        {
            "artifact_type": "planner_order",
            "round": 1,
            "round_goal": "Do work.",
            "plan_graph": {
                "work_items": [
                    {
                        "work_item_id": "work",
                        "merge_index": 1,
                        "assignee_agent_id": "executor",
                        "task_summary": "Implement.",
                        "depends_on": [],
                    }
                ]
            },
        }
    )


if __name__ == "__main__":
    unittest.main()
