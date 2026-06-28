from __future__ import annotations

import inspect
import tempfile
import unittest

from coder_workbench.actions.schema import ACTION_TYPES
from coder_workbench.agent_graph.runner import AgentGraphRunner
from coder_workbench.core import default_planner_led_agent_workflow


class CurrentProductContractTests(unittest.TestCase):
    def test_product_action_surface_contains_agentgraph_capability_matrix(self) -> None:
        self.assertIn("repo_index", ACTION_TYPES)
        self.assertIn("call_plugin", ACTION_TYPES)
        self.assertIn("call_mcp", ACTION_TYPES)
        self.assertIn("run_command_sandbox", ACTION_TYPES)
        self.assertIn("run_command", ACTION_TYPES)

    def test_product_runner_source_uses_runtime_services(self) -> None:
        source = inspect.getsource(AgentGraphRunner)

        self.assertIn("RunController", source)
        self.assertIn("ActionGateway", source)

    def test_default_product_run_produces_agentgraph_contract_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = AgentGraphRunner(default_planner_led_agent_workflow()).run("Check current contract.", tmp)

        self.assertEqual(result.status, "completed")
        artifact_types = {
            artifact.get("artifact_type")
            for artifact in result.artifacts.values()
            if isinstance(artifact, dict)
        }
        self.assertIn("planner_order", artifact_types)
        self.assertIn("planner_input_bundle", artifact_types)
        self.assertIn("planner_decision", artifact_types)
        self.assertFalse({"plan_artifact", "patch_artifact", "review_artifact"}.intersection(artifact_types))


if __name__ == "__main__":
    unittest.main()
