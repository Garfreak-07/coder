from __future__ import annotations

import unittest

from coder_workbench.agent_harness.artifact_repair_pipeline import (
    ArtifactRepairPipeline,
    RepairContext,
)


class ArtifactRepairPipelineTests(unittest.TestCase):
    def test_malformed_json_is_repaired_by_extraction(self) -> None:
        output = 'Here is JSON:\n{"artifact_type":"execution_result","status":"completed","summary":"Done."}'

        outcome = ArtifactRepairPipeline().repair(
            expected_type="execution_result",
            invalid_output=output,
            context=RepairContext(agent_id="executor", work_item_id="work", merge_index=1),
        )

        self.assertEqual(outcome.status, "ok")
        self.assertEqual(outcome.stage, "deterministic_schema_patch")
        self.assertEqual(outcome.artifact["summary"], "Done.")

    def test_missing_safe_fields_are_deterministically_filled(self) -> None:
        outcome = ArtifactRepairPipeline().repair(
            expected_type="execution_result",
            invalid_output='{"summary":"Needs planner."}',
            context=RepairContext(agent_id="executor", work_item_id="work", merge_index=3, round_number=2),
        )

        self.assertEqual(outcome.status, "ok")
        self.assertEqual(outcome.stage, "deterministic_schema_patch")
        self.assertEqual(outcome.artifact["work_item_id"], "work")
        self.assertEqual(outcome.artifact["merge_index"], 3)
        self.assertEqual(outcome.artifact["agent_id"], "executor")
        self.assertEqual(outcome.artifact["round"], 2)

    def test_invalid_artifact_triggers_model_repair_once(self) -> None:
        model = CountingModel(
            [
                '{"artifact_type":"execution_result","status":"completed","summary":"Repaired."}'
            ]
        )

        outcome = ArtifactRepairPipeline().repair(
            expected_type="execution_result",
            invalid_output="not json",
            model=model,
            context=RepairContext(agent_id="executor", work_item_id="work", merge_index=1),
        )

        self.assertEqual(outcome.status, "ok")
        self.assertEqual(outcome.stage, "model_repair")
        self.assertTrue(outcome.repair_used)
        self.assertEqual(model.calls, 1)
        self.assertEqual(outcome.artifact["summary"], "Repaired.")

    def test_failed_repair_returns_blocked_artifact(self) -> None:
        model = CountingModel(["still not json"])

        outcome = ArtifactRepairPipeline().repair(
            expected_type="execution_result",
            invalid_output="not json",
            model=model,
            context=RepairContext(agent_id="executor", work_item_id="work", merge_index=1),
        )

        self.assertEqual(outcome.status, "blocked")
        self.assertEqual(outcome.stage, "safe_fallback_artifact")
        self.assertEqual(outcome.artifact["status"], "blocked")
        self.assertEqual(outcome.artifact["blocker_type"], "schema_validation_failed")
        self.assertEqual(model.calls, 1)


class CountingResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class CountingModel:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls = 0

    def invoke(self, prompt: str) -> CountingResponse:
        self.calls += 1
        return CountingResponse(self.responses.pop(0))


if __name__ == "__main__":
    unittest.main()
