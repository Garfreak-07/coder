import unittest

from coder_workbench.agent_model import AgentRecipe, RuntimeProfileCompiler


class RuntimeProfileClosureTests(unittest.TestCase):
    def test_planner_and_executor_profiles_use_agentgraph_artifacts(self) -> None:
        compiler = RuntimeProfileCompiler()
        planner = compiler.compile(AgentRecipe(id="planner", name="Planner", role="planner"))
        executor = compiler.compile(AgentRecipe(id="executor", name="Executor", role="executor"))

        self.assertEqual(planner.allowed_artifacts, ["run_contract", "planner_order", "planner_decision", "round_summary"])
        self.assertIsNone(planner.harness_id)
        self.assertEqual(executor.allowed_artifacts, ["execution_result"])
        self.assertEqual(executor.harness_id, "code-worker-harness")

    def test_executor_profile_can_run_commands_for_verification(self) -> None:
        executor = RuntimeProfileCompiler().compile(AgentRecipe(id="executor", name="Executor", role="executor"))

        self.assertTrue(executor.tool_policy["read_files"])
        self.assertTrue(executor.tool_policy["write_files"])
        self.assertTrue(executor.tool_policy["run_commands"])
        self.assertFalse(executor.tool_policy["ask_human"])


if __name__ == "__main__":
    unittest.main()
