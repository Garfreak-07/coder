from __future__ import annotations

import unittest

from coder_workbench.core import default_planner_led_agent_workflow
from coder_workbench.core.agent_workflow import VALID_AGENT_ROLES


class ProductRolesOnlyTests(unittest.TestCase):
    def test_only_planner_executor_tester_roles_are_valid(self) -> None:
        self.assertEqual(VALID_AGENT_ROLES, {"planner", "executor", "tester"})

    def test_default_workflow_is_minimal_planner_executor_tester_loop(self) -> None:
        workflow = default_planner_led_agent_workflow()

        self.assertEqual([agent.role for agent in workflow.agents], ["planner", "executor", "tester"])
        self.assertEqual([agent.id for agent in workflow.agents], ["planner", "executor", "tester"])
        self.assertEqual(
            [(edge.from_agent, edge.to_agent, edge.loop) for edge in workflow.edges],
            [
                ("planner", "executor", False),
                ("executor", "tester", False),
                ("tester", "planner", True),
            ],
        )

    def test_default_executor_and_tester_use_role_cards(self) -> None:
        workflow = default_planner_led_agent_workflow()
        agents = {agent.id: agent for agent in workflow.agents}

        self.assertIsNone(agents["planner"].role_card)
        self.assertEqual(agents["executor"].role_card, "executor")
        self.assertEqual(agents["tester"].role_card, "tester")


if __name__ == "__main__":
    unittest.main()
