from __future__ import annotations

import tempfile
import unittest

from coder_workbench.agent_graph.runner import AgentGraphRunner
from coder_workbench.agent_harness.contracts import (
    CODE_WORKER_HARNESS,
    FINAL_REPORT_HARNESS,
    PLANNER_DECISION_HARNESS,
    PLANNER_ORDER_HARNESS,
    harness_contract_for_id,
)
from coder_workbench.agent_model import AgentRecipe, RuntimeProfileCompiler
from coder_workbench.core import default_planner_led_agent_workflow
from coder_workbench.runtime_capabilities import resolve_capabilities


class HarnessContractTests(unittest.TestCase):
    def test_current_harness_contracts_are_explicit(self) -> None:
        self.assertEqual(harness_contract_for_id(PLANNER_ORDER_HARNESS.harness_id).output_artifacts, ["planner_order"])
        self.assertEqual(harness_contract_for_id(PLANNER_DECISION_HARNESS.harness_id).output_artifacts, ["planner_decision"])
        self.assertEqual(harness_contract_for_id(FINAL_REPORT_HARNESS.harness_id).output_artifacts, ["final_report"])
        self.assertEqual(harness_contract_for_id(CODE_WORKER_HARNESS.harness_id).output_artifacts, ["execution_result"])
        self.assertFalse(PLANNER_ORDER_HARNESS.may_write_files)
        self.assertTrue(CODE_WORKER_HARNESS.may_write_files)
        self.assertFalse(CODE_WORKER_HARNESS.may_talk_to_user)

    def test_runtime_profile_records_executor_harness_id(self) -> None:
        compiler = RuntimeProfileCompiler()
        planner = compiler.compile(AgentRecipe(id="planner", name="Planner", role="planner"))
        executor = compiler.compile(AgentRecipe(id="executor", name="Executor", role="executor"))

        self.assertIsNone(planner.harness_id)
        self.assertEqual(executor.harness_id, CODE_WORKER_HARNESS.harness_id)


class RuntimeCapabilityResolverTests(unittest.TestCase):
    def test_planner_and_executor_capabilities_are_split(self) -> None:
        workflow = default_planner_led_agent_workflow()
        compiler = RuntimeProfileCompiler()
        planner = workflow.agents[0]
        executor = workflow.agents[1]
        planner_profile = compiler.compile(AgentRecipe(id=planner.id, name=planner.name, role=planner.role))
        executor_profile = compiler.compile(AgentRecipe(id=executor.id, name=executor.name, role=executor.role))

        planner_caps = resolve_capabilities(
            agent=planner,
            runtime_profile=planner_profile,
            harness_id=PLANNER_DECISION_HARNESS.harness_id,
            state_view={"round": 1},
            installed_capabilities=[],
        )
        executor_caps = resolve_capabilities(
            agent=executor,
            runtime_profile=executor_profile,
            harness_id=CODE_WORKER_HARNESS.harness_id,
            work_item={"work_item_id": "executor-work"},
            state_view={"assigned_work_item": {"work_item_id": "executor-work"}},
            installed_capabilities={"allowed_skill_ids": ["execution_verification"]},
        )

        self.assertIn("inspect_run_state", {tool.name for tool in planner_caps.tools})
        self.assertIn("run_command_sandbox", {tool.name for tool in executor_caps.tools})
        self.assertIn("push", {capability.name for capability in planner_caps.denied})
        self.assertIn("ask_user", {capability.name for capability in executor_caps.denied})
        self.assertEqual(executor_caps.skills[0].skill_id, "execution_verification")

    def test_agent_run_records_capability_sets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = AgentGraphRunner(default_planner_led_agent_workflow()).run(
                "Resolve capabilities.",
                tmp,
            )

        records = result.data["capability_sets"]
        harnesses = {record["harness_id"] for record in records}

        self.assertIn(PLANNER_ORDER_HARNESS.harness_id, harnesses)
        self.assertIn(PLANNER_DECISION_HARNESS.harness_id, harnesses)
        self.assertIn(CODE_WORKER_HARNESS.harness_id, harnesses)
        by_harness = result.data["capability_sets_by_harness"]
        executor_caps = by_harness[f"executor:{CODE_WORKER_HARNESS.harness_id}"]
        self.assertIn("return_execution_result", {tool["name"] for tool in executor_caps["tools"]})


if __name__ == "__main__":
    unittest.main()
