import unittest

from coder_workbench.core.agent_workflow import VALID_AGENT_ROLES, default_planner_led_agent_workflow


class ProductRolesOnlyTests(unittest.TestCase):
    def test_only_planner_executor_roles_are_valid(self) -> None:
        self.assertEqual(VALID_AGENT_ROLES, {"planner", "executor"})

    def test_default_workflow_is_minimal_planner_executor_loop(self) -> None:
        workflow = default_planner_led_agent_workflow()

        self.assertEqual([agent.role for agent in workflow.agents], ["planner", "executor"])
        self.assertEqual([agent.id for agent in workflow.agents], ["planner", "executor"])
        self.assertEqual(
            [(edge.from_agent, edge.to_agent, edge.loop) for edge in workflow.edges],
            [
                ("planner", "executor", False),
                ("executor", "planner", True),
            ],
        )

    def test_default_executor_uses_execution_capabilities(self) -> None:
        workflow = default_planner_led_agent_workflow()
        executor = workflow.agents[1]

        self.assertEqual(executor.role_card, "executor")
        self.assertIn("optional_check_command", executor.capabilities)
        self.assertIn("return_execution_result", executor.capabilities)


if __name__ == "__main__":
    unittest.main()
