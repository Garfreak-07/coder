import unittest

from coder_workbench.agent_model import AgentRecipe, RuntimeProfileCompiler
from coder_workbench.core import AgentWorkflowSpec, default_planner_led_agent_workflow


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

    def test_workflow_profiles_include_harness_runtime_refs(self) -> None:
        workflow = default_planner_led_agent_workflow()
        payload = workflow.model_dump(mode="json", by_alias=True)
        payload["agents"][1]["runtime_profile_id"] = "custom-task-profile"
        workflow = AgentWorkflowSpec.model_validate(payload)

        profiles = RuntimeProfileCompiler().compile_workflow(workflow)
        planner = next(profile for profile in profiles if profile.agent_id == "planner")
        executor = next(profile for profile in profiles if profile.agent_id == "executor")

        self.assertEqual(planner.harness_runtime_profile_id, "openhands-workflow-supervisor-default")
        self.assertEqual(planner.harness_provider_id, "openhands-sdk")
        self.assertEqual(planner.harness_mode, "workflow_supervisor")
        self.assertEqual(executor.harness_runtime_profile_id, "custom-task-profile")
        self.assertEqual(executor.harness_provider_id, "openhands-sdk")
        self.assertEqual(executor.harness_mode, "task_execution")


if __name__ == "__main__":
    unittest.main()
