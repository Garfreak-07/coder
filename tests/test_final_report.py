from __future__ import annotations

import tempfile
import unittest

from coder_workbench.agent_graph.final_report import build_final_report
from coder_workbench.agent_graph.runner import AgentGraphRunner
from coder_workbench.core.artifacts import supported_artifact_types, validate_artifact
from coder_workbench.core import default_planner_led_agent_workflow


class FinalReportTests(unittest.TestCase):
    def test_final_report_artifact_validates(self) -> None:
        artifact = validate_artifact(
            {
                "artifact_type": "final_report",
                "status": "completed",
                "summary": "Run completed.",
                "files": {"created": [], "modified": ["src/app.py"], "deleted": []},
                "checks": [
                    {
                        "command": "python -m unittest",
                        "status": "passed",
                        "summary": "Tests passed.",
                        "output_ref": "check-output",
                        "evidence_refs": ["check-output"],
                    }
                ],
                "completed": ["executor-work: Updated app."],
                "evidence_refs": ["patch-1", "check-output"],
            },
            expected_type="final_report",
            artifact_id="final_report",
        )

        self.assertIn("final_report", supported_artifact_types())
        self.assertEqual(artifact["artifact_type"], "final_report")
        self.assertEqual(artifact["artifact_id"], "final_report")
        self.assertEqual(artifact["checks"][0]["status"], "passed")

    def test_build_completed_final_report(self) -> None:
        report = build_final_report(
            status="completed",
            data={},
            artifacts={
                "execution_result_round_1": _execution_result(
                    status="completed",
                    summary="Implemented the change.",
                    changed_files=["src/app.py"],
                    evidence_refs=["patch-1"],
                    verification_status="pass",
                )
            },
            events=[],
        )

        self.assertEqual(report["status"], "completed")
        self.assertEqual(report["files"]["modified"], ["src/app.py"])
        self.assertEqual(report["checks"][0]["status"], "passed")
        self.assertEqual(report["evidence_refs"], ["patch-1", "check-output"])
        self.assertEqual(report["blocked_by"], [])

    def test_build_blocked_final_report(self) -> None:
        report = build_final_report(
            status="blocked",
            status_reason="Dependency is unavailable.",
            status_code="missing_dependency",
            data={},
            artifacts={
                "execution_result_round_1": _execution_result(
                    status="blocked",
                    summary="Cannot run check command.",
                    blocker_type="dependency_missing",
                    verification_status="blocked",
                    remaining_work=["Install the missing command."],
                )
            },
            events=[],
        )

        self.assertEqual(report["status"], "blocked")
        self.assertIn("dependency_missing: Cannot run check command.", report["blocked_by"])
        self.assertIn("Dependency is unavailable.", report["blocked_by"])
        self.assertTrue(report["next_steps"])
        self.assertIn("Run status code: missing_dependency.", report["notes"])

    def test_build_failed_final_report(self) -> None:
        report = build_final_report(
            status="failed",
            status_reason="Runner raised an exception.",
            data={},
            artifacts={
                "execution_result_round_1": _execution_result(
                    status="blocked",
                    summary="Verification failed.",
                    blocker_type="verification_failed",
                    verification_status="fail",
                )
            },
            events=[],
        )

        self.assertEqual(report["status"], "failed")
        self.assertIn("Runner raised an exception.", report["failed_by"])
        self.assertTrue(report["next_steps"])

    def test_build_final_report_from_shared_run_state_fallback(self) -> None:
        report = build_final_report(
            status="completed",
            data={
                "shared_run_state": {
                    "run_id": "run",
                    "workflow_id": "workflow",
                    "user_request": "Do work.",
                    "control": {"status": "completed", "round": 1, "blocked_recovery_used": False},
                    "planner": {},
                    "work_items": {
                        "work": {
                            "work_item_id": "work",
                            "agent_id": "executor",
                            "status": "completed",
                            "summary": "Completed from shared state.",
                            "execution_result_ref": "execution_result_work",
                        }
                    },
                    "messages": [],
                    "artifacts": {},
                    "tool_results": {},
                    "blobs": {},
                    "memory_refs": [],
                    "final_report_ref": None,
                    "debug_refs": [],
                }
            },
            artifacts={},
            events=[],
        )

        self.assertEqual(report["status"], "completed")
        self.assertEqual(report["completed"], ["work: Completed from shared state."])
        self.assertEqual(report["evidence_refs"], ["execution_result_work"])

    def test_runner_stores_final_report_and_compact_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = AgentGraphRunner(default_planner_led_agent_workflow()).run("Check final report.", tmp)

        self.assertEqual(result.status, "completed")
        self.assertIn("final_report", result.data)
        self.assertEqual(result.data["final_report"]["artifact_type"], "final_report")
        self.assertEqual(result.artifacts["final_report"]["artifact_type"], "final_report")
        compact_event = next(event for event in result.events if event.type == "final_report.created")
        self.assertEqual(
            set(compact_event.payload),
            {"artifact_type", "artifact_id", "status", "summary", "evidence_count"},
        )


def _execution_result(
    *,
    status: str,
    summary: str,
    verification_status: str,
    changed_files: list[str] | None = None,
    evidence_refs: list[str] | None = None,
    blocker_type: str | None = None,
    remaining_work: list[str] | None = None,
) -> dict:
    return {
        "artifact_type": "execution_result",
        "round": 1,
        "work_item_id": "executor-work",
        "agent_id": "executor",
        "status": status,
        "summary": summary,
        "changed_files": changed_files or [],
        "evidence_refs": evidence_refs or [],
        "remaining_work": remaining_work or [],
        "unexpected_issues": [blocker_type] if blocker_type else [],
        "needs_planner_decision": status == "blocked",
        "blocker_type": blocker_type,
        "verification": {
            "status": verification_status,
            "checks_run": [
                {
                    "check_id": "check-1",
                    "kind": "command",
                    "command": "python -m unittest",
                    "status": verification_status,
                    "summary": "Check completed." if verification_status == "pass" else "Check did not pass.",
                    "output_ref": "check-output",
                    "evidence_refs": ["check-output"],
                }
            ],
            "evidence_refs": evidence_refs or [],
            "confidence": "medium",
            "remaining_work": remaining_work or [],
        },
    }


if __name__ == "__main__":
    unittest.main()
