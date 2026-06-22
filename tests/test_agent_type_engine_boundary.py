from __future__ import annotations

import unittest

from coder_workbench.agent_engine import (
    CodeWorkerEngine,
    PlannerEngine,
    TesterEngine,
    default_agent_engine_registry,
)
from coder_workbench.agent_model import AgentRecipe, RuntimeProfileCompiler
from coder_workbench.core import role_card_registry
from coder_workbench.core.artifacts import supported_artifact_types


class AgentTypeEngineBoundaryTests(unittest.TestCase):
    def test_role_cards_map_directly_to_engines(self) -> None:
        cards = role_card_registry()

        self.assertEqual(sorted(cards), ["executor", "tester"])
        self.assertEqual(cards["executor"].role, "executor")
        self.assertEqual(cards["executor"].archetype, "executor")
        self.assertEqual(cards["executor"].engine_id, "code-worker-engine")
        self.assertEqual(cards["tester"].role, "tester")
        self.assertEqual(cards["tester"].archetype, "tester")
        self.assertEqual(cards["tester"].engine_id, "tester-engine")
        self.assertEqual(
            sorted({card.engine_id for card in cards.values()}),
            ["code-worker-engine", "tester-engine"],
        )

    def test_default_registry_only_contains_product_engines(self) -> None:
        registry = default_agent_engine_registry()

        self.assertEqual(
            registry.ids(),
            ["code-worker-engine", "planner-engine", "tester-engine"],
        )
        self.assertIsInstance(registry.get("planner-engine"), PlannerEngine)
        self.assertIsInstance(registry.get("code-worker-engine"), CodeWorkerEngine)
        self.assertIsInstance(registry.get("tester-engine"), TesterEngine)

    def test_removed_engines_and_artifacts_are_not_supported(self) -> None:
        import coder_workbench.agent_engine.runtime as runtime

        self.assertFalse(hasattr(runtime, "SynthesizerEngine"))
        self.assertFalse(hasattr(runtime, "FinalReviewEngine"))
        self.assertNotIn("synthesis_artifact", supported_artifact_types())

    def test_runtime_profiles_restrict_engine_artifact_outputs(self) -> None:
        compiler = RuntimeProfileCompiler()

        planner = compiler.compile(AgentRecipe(id="planner", name="Planner", role="planner"))
        executor = compiler.compile(AgentRecipe(id="executor", name="Executor", role="executor"))
        tester = compiler.compile(AgentRecipe(id="tester", name="Tester", role="tester"))

        self.assertEqual(planner.engine_id, "planner-engine")
        self.assertEqual(
            planner.allowed_artifacts,
            ["run_contract", "planner_order", "planner_decision", "round_summary"],
        )
        self.assertEqual(executor.engine_id, "code-worker-engine")
        self.assertEqual(executor.allowed_artifacts, ["execution_result"])
        self.assertEqual(tester.engine_id, "tester-engine")
        self.assertEqual(tester.allowed_artifacts, ["test_result"])

    def test_removed_role_card_ids_are_absent(self) -> None:
        self.assertTrue(
            {
                "do_work",
                "check_result",
                "organize_information",
                "research_sources",
                "write_draft",
            }.isdisjoint(role_card_registry())
        )


if __name__ == "__main__":
    unittest.main()
