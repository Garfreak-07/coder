from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from coder_workbench.actions import ActionGateway, ActionSpec, RunContext
from coder_workbench.agent_graph.cache import GraphRunCache
from coder_workbench.agent_graph.schema import WorkItem
from coder_workbench.context import ContextBudget, ContextCompactor, ContextExternalRefStore
from coder_workbench.skills import SkillIndex


class ContextCompactionTests(unittest.TestCase):
    def test_large_tool_result_gets_externalized(self) -> None:
        store = ContextExternalRefStore({})
        packet = {
            "artifact_type": "execution_result",
            "work_item_id": "work-1",
            "status": "blocked",
            "summary": "Command blocked.",
            "command_output": "error line\n" * 1000,
        }

        result = ContextCompactor(
            ContextBudget(max_input_tokens=80, max_artifact_tokens=20, max_tool_result_tokens=20)
        ).compact(packet, run_id="run", work_item_id="work-1", store=store)

        output = result.packet["command_output"]
        self.assertTrue(output["truncated"])
        self.assertIn(output["full_ref"], store.backing)
        self.assertEqual(store.read(output["full_ref"])["content"], "error line\n" * 1000)
        self.assertLess(result.token_estimate_after, result.token_estimate_before)

    def test_artifact_identity_failure_reason_and_evidence_refs_survive(self) -> None:
        store = ContextExternalRefStore({})
        packet = {
            "artifact_id": "execution_result_work-1",
            "artifact_type": "execution_result",
            "work_item_id": "work-1",
            "round": 2,
            "status": "blocked",
            "failure_reason": "verification failed",
            "evidence_refs": ["execution_result_work-1"],
            "output": "x" * 5000,
        }

        result = ContextCompactor(
            ContextBudget(max_input_tokens=80, max_artifact_tokens=20, max_tool_result_tokens=20)
        ).compact(packet, run_id="run", work_item_id="work-1", store=store)

        self.assertEqual(result.packet["artifact_id"], "execution_result_work-1")
        self.assertEqual(result.packet["artifact_type"], "execution_result")
        self.assertEqual(result.packet["work_item_id"], "work-1")
        self.assertEqual(result.packet["round"], 2)
        self.assertEqual(result.packet["status"], "blocked")
        self.assertEqual(result.packet["failure_reason"], "verification failed")
        self.assertEqual(result.packet["evidence_refs"], ["execution_result_work-1"])

    def test_action_gateway_build_context_applies_context_compaction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "src" / "large.py"
            target.parent.mkdir()
            target.write_text("value = '" + ("x" * 5000) + "'\n", encoding="utf-8")
            cache = GraphRunCache(round=1)
            item = WorkItem(
                work_item_id="executor-work",
                merge_index=1,
                assignee_agent_id="executor",
                task_summary="Inspect src/large.py.",
                depends_on=[],
            )

            result = ActionGateway().run(
                ActionSpec(action_id="ctx", action_type="build_context"),
                run_context=RunContext(
                    run_id="run",
                    repo_root=root,
                    cache=cache,
                    item=item,
                    planner_order_ref="planner_order_round_1",
                    upstream_refs=[],
                    user_request="Inspect src/large.py.",
                    role="executor",
                    skill_index=SkillIndex(),
                    skill_store_root=root / ".coder",
                    repo_intelligence={"repo_index": {"important_files": ["src/large.py"]}},
                    data={
                        "enable_context_compaction": True,
                        "context_budget": {
                            "max_input_tokens": 120,
                            "max_artifact_tokens": 20,
                            "max_tool_result_tokens": 20,
                        },
                    },
                ),
            )

        self.assertEqual(result.status, "ok")
        self.assertIn("executor-work", cache.context_compactions)
        self.assertTrue(cache.context_external_refs)
        compact_packet = result.payload["compact_coding_context_packet"]
        snippet_content = compact_packet["included_snippets"][0]["content"]
        self.assertTrue(snippet_content["truncated"])
        self.assertIn(snippet_content["full_ref"], cache.context_external_refs)


if __name__ == "__main__":
    unittest.main()
