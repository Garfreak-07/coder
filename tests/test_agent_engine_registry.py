import unittest

from coder_workbench.agent_engine import CodeWorkerEngine, PlannerEngine, default_agent_engine_registry


class AgentEngineRegistryTests(unittest.TestCase):
    def test_default_registry_exposes_only_planner_and_executor_engines(self) -> None:
        registry = default_agent_engine_registry()

        self.assertEqual(registry.ids(), ["code-worker-engine", "planner-engine"])
        self.assertIsInstance(registry.planner(), PlannerEngine)
        self.assertIsInstance(registry.get("code-worker-engine"), CodeWorkerEngine)
        with self.assertRaises(KeyError):
            registry.get("tester-engine")


if __name__ == "__main__":
    unittest.main()
