import unittest

from coder_workbench.agent_engine import default_agent_engine_registry
from coder_workbench.agent_model import AgentRecipe, RuntimeProfileCompiler
from coder_workbench.core import default_planner_led_agent_workflow, role_card_registry


class AgentTypeEngineBoundaryTests(unittest.TestCase):
    def test_role_cards_are_executor_only(self) -> None:
        cards = role_card_registry()

        self.assertEqual(sorted(cards), ["executor"])
        self.assertEqual(cards["executor"].role, "executor")
        self.assertEqual(cards["executor"].engine_id, "code-worker-engine")

    def test_default_registry_has_no_tester_engine(self) -> None:
        registry = default_agent_engine_registry()

        self.assertEqual(registry.ids(), ["code-worker-engine", "planner-engine"])
        with self.assertRaises(KeyError):
            registry.get("tester-engine")

    def test_runtime_profile_compiler_maps_executor_to_execution_result(self) -> None:
        compiler = RuntimeProfileCompiler()
        planner = compiler.compile(AgentRecipe(id="planner", name="Planner", role="planner"))
        executor = compiler.compile(AgentRecipe(id="executor", name="Executor", role="executor"))

        self.assertEqual(planner.engine_id, "planner-engine")
        self.assertEqual(planner.allowed_artifacts, ["run_contract", "planner_order", "planner_decision", "round_summary"])
        self.assertEqual(executor.engine_id, "code-worker-engine")
        self.assertEqual(executor.allowed_artifacts, ["execution_result"])
        self.assertTrue(executor.tool_policy["run_commands"])

    def test_default_workflow_profiles_are_two_role(self) -> None:
        profiles = RuntimeProfileCompiler().compile_workflow(default_planner_led_agent_workflow())

        self.assertEqual([profile.role for profile in profiles], ["planner", "executor"])
        self.assertEqual([profile.engine_id for profile in profiles], ["planner-engine", "code-worker-engine"])


if __name__ == "__main__":
    unittest.main()
