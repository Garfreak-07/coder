from __future__ import annotations

import inspect
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from coder_workbench.actions.schema import ACTION_TYPES
from coder_workbench.agent_graph.runner import AgentGraphRunner
from coder_workbench.core import default_planner_led_agent_workflow
from coder_workbench.server.app import create_app


ROOT = Path(__file__).resolve().parents[1]


class OnePointZeroContractTests(unittest.TestCase):
    def test_release_docs_exist_and_name_contract_freeze(self) -> None:
        required = [
            ROOT / "docs" / "release-1.0-plan.md",
            ROOT / "docs" / "runtime-action-contract.md",
            ROOT / "docs" / "1.0-acceptance-tests.md",
        ]

        for path in required:
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertIn("v1.0", text)

        self.assertIn("contract freeze", (ROOT / "docs" / "release-1.0-plan.md").read_text(encoding="utf-8").lower())

    def test_readme_names_v0_9_7_and_frozen_product_path(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("v0.9.7 v1.0 convergence plan", readme)
        for token in [
            "AgentWorkflowSpec",
            "PlannerOrder.plan_graph",
            "RunController / RunGuard",
            "BudgetBroker round preflight",
            "GraphRunCache",
            "ActionGateway",
            "ContextService",
            "AgentRun",
            "PlannerStrategy",
            "AgentEngineRegistry",
            "PlannerInputBundle",
            "PlannerDecision",
        ]:
            with self.subTest(token=token):
                self.assertIn(token, readme)

    def test_runtime_action_contract_covers_audit_replay_metadata(self) -> None:
        text = (ROOT / "docs" / "runtime-action-contract.md").read_text(encoding="utf-8")

        for token in [
            "RuntimeActionRecord",
            "approval_key",
            "policy",
            "ActionSpec",
            "work_item_id",
            "approved_runtime_actions",
            "ActionGateway",
            "must not re-run the worker model",
        ]:
            with self.subTest(token=token):
                self.assertIn(token, text)

    def test_product_action_surface_contains_v1_0_capability_matrix(self) -> None:
        self.assertIn("repo_index", ACTION_TYPES)
        self.assertIn("call_plugin", ACTION_TYPES)
        self.assertIn("call_mcp", ACTION_TYPES)
        self.assertIn("run_command_sandbox", ACTION_TYPES)
        self.assertIn("run_command", ACTION_TYPES)

    def test_product_runner_source_keeps_legacy_runtime_isolated(self) -> None:
        source = inspect.getsource(AgentGraphRunner)

        self.assertNotIn("WorkflowRunner", source)
        self.assertNotIn("compile_agent_workflow", source)
        self.assertIn("RunController", source)
        self.assertIn("ActionGateway", source)

    def test_legacy_live_runs_endpoint_remains_deprecated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with TestClient(create_app(store_root=tmp, frontend_dist=str(ROOT))) as client:
                response = client.get("/api/v2/live-runs")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["deprecated"])

    def test_default_product_run_produces_agentgraph_contract_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = AgentGraphRunner(default_planner_led_agent_workflow()).run("Check 1.0 contract.", tmp)

        self.assertEqual(result.status, "completed")
        artifact_types = {artifact.get("artifact_type") for artifact in result.artifacts.values() if isinstance(artifact, dict)}
        self.assertIn("planner_order", artifact_types)
        self.assertIn("planner_input_bundle", artifact_types)
        self.assertIn("planner_decision", artifact_types)
        self.assertFalse({"plan_artifact", "patch_artifact", "review_artifact"}.intersection(artifact_types))


if __name__ == "__main__":
    unittest.main()
