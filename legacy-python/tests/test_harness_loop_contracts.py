from __future__ import annotations

import unittest

from pydantic import ValidationError

from coder_workbench.harness_runtime import HarnessLoopLimits, HarnessLoopStep, HarnessLoopTrace


class HarnessLoopContractTests(unittest.TestCase):
    def test_trace_models_validate(self) -> None:
        trace = HarnessLoopTrace(
            run_id="run-1",
            request_id="request-1",
            harness_id="conversation-harness",
            mode="workflow_supervisor",
            provider_id="openhands",
            artifact_target="planner_order",
            limits=HarnessLoopLimits(max_model_turns=4),
            steps=[
                HarnessLoopStep(
                    step_index=0,
                    phase="started",
                    mode="workflow_supervisor",
                    artifact_target="planner_order",
                    agent_id="planner",
                    summary="Started.",
                    native_event_refs=["event-1"],
                )
            ],
        )

        self.assertEqual(trace.limits.max_model_turns, 4)
        self.assertEqual(trace.steps[0].phase, "started")

    def test_trace_model_rejects_invalid_phase(self) -> None:
        with self.assertRaises(ValidationError):
            HarnessLoopStep(
                step_index=0,
                phase="not-a-phase",  # type: ignore[arg-type]
                mode="workflow_supervisor",
                summary="Invalid.",
            )


if __name__ == "__main__":
    unittest.main()
