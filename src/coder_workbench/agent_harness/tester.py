from __future__ import annotations

from typing import Any

from coder_workbench.agent_graph.artifacts import graph_artifact_id
from coder_workbench.agent_graph.schema import TestRecord, WorkItem
from coder_workbench.agent_harness.self_check import TesterSelfChecker, harness_self_check_enabled
from coder_workbench.coding.checks import run_check_command

from .base import AgentHarness
from .policies import tester_policy


class TestHarness(AgentHarness):
    def __init__(self, *, enable_self_check: bool | None = None) -> None:
        super().__init__(policy=tester_policy())
        self.enable_self_check = harness_self_check_enabled(enable_self_check)

    def create_test_result(
        self,
        *,
        repo_root: str,
        item: WorkItem,
        tester_agent_id: str,
        execution_artifact: dict[str, Any],
        check_commands: list[dict[str, Any]] | None = None,
    ) -> TestRecord:
        checks = [
            run_check_command(repo_root, str(command.get("command") or ""), cwd=str(command.get("cwd") or "."))
            for command in (check_commands or [])
            if command.get("command")
        ]
        status = "pass"
        if any(check.status == "blocked" for check in checks):
            status = "blocked"
        elif any(check.status == "fail" for check in checks):
            status = "fail"
        summary = "TestHarness found no blocking issue." if status == "pass" else "TestHarness found failing or blocked checks."
        artifact = {
            "artifact_type": "test_result",
            "round": int(execution_artifact.get("round") or 1),
            "work_item_id": item.work_item_id,
            "merge_index": item.merge_index,
            "tester_agent_id": tester_agent_id,
            "status": status,
            "summary": summary,
            "evidence": [check.output_ref for check in checks if check.output_ref],
            "issues": [],
            "remaining_work": [] if status == "pass" else [check.summary for check in checks if check.status != "pass"],
            "confidence": "medium",
            "check_commands": [str(command.get("command") or "") for command in (check_commands or []) if command.get("command")],
            "check_outputs_ref": None,
        }
        if self.enable_self_check:
            evidence_refs = [str(execution_artifact.get("artifact_id") or "")] if execution_artifact.get("artifact_id") else []
            artifact = TesterSelfChecker().check(
                artifact,
                item=item,
                tester_agent_id=tester_agent_id,
                evidence_refs=evidence_refs,
                round_number=int(execution_artifact.get("round") or 1),
            ).artifact
        return TestRecord(
            work_item_id=item.work_item_id,
            merge_index=item.merge_index,
            tester_agent_id=tester_agent_id,
            status=status,
            test_summary=summary,
            test_result_ref=graph_artifact_id("test_result", item.work_item_id, tester_agent_id),
            artifact_payload=artifact,
        )
