from __future__ import annotations

import unittest

from coder_workbench.agent_engine import default_agent_engine_registry
from coder_workbench.agent_model import AgentRecipe, RuntimeProfileCompiler


class RuntimeProfileClosureTests(unittest.TestCase):
    def test_all_recipe_roles_compile_to_registered_default_engines(self) -> None:
        registry = default_agent_engine_registry()
        compiler = RuntimeProfileCompiler()

        for role in ["planner", "executor", "tester"]:
            profile = compiler.compile(
                AgentRecipe(id=f"{role}-agent", name=f"{role} Agent", role=role)
            )
            self.assertIn(profile.engine_id, registry.ids(), role)

    def test_executor_and_tester_profiles_use_agentgraph_artifacts(self) -> None:
        compiler = RuntimeProfileCompiler()

        executor = compiler.compile(AgentRecipe(id="executor", name="Executor", role="executor"))
        tester = compiler.compile(AgentRecipe(id="tester", name="Tester", role="tester"))

        self.assertEqual(executor.engine_id, "code-worker-engine")
        self.assertEqual(executor.allowed_artifacts, ["execution_result"])
        self.assertEqual(tester.engine_id, "tester-engine")
        self.assertEqual(tester.allowed_artifacts, ["test_result"])


if __name__ == "__main__":
    unittest.main()
