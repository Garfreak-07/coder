from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from coder_workbench.context import build_harness_context_packet
from coder_workbench.context.agentic_router import AgenticContextRouter
from coder_workbench.context.evidence_policy import code_fact_supported_by_evidence_kind, rag_evidence_metadata
from coder_workbench.context.repo_context_service import NativeRepoContextService
from coder_workbench.context.repo_read import RepoReadService
from coder_workbench.openhands_tools.repo_context import (
    CoderRepoFindFilesAction,
    CoderRepoReadFileAction,
    CoderRepoSearchTextAction,
)


class AgenticNativeContextFreezeTests(unittest.TestCase):
    def test_freeze_core_routing_and_evidence_invariants(self) -> None:
        with _repo() as root:
            (root / "src" / "app.py").write_text("class PlannerTaskState:\n    pass\n", encoding="utf-8")
            router = AgenticContextRouter(
                coder_store_root=root / ".coder",
                repo_root=root,
                run_id="run-1",
                mode="planning_chat",
            )

            code_state = router.route("Where is PlannerTaskState defined?")
            roadmap_state = router.route("What roadmap decision did we make for Obsidian?")
            task_state = AgenticContextRouter(
                coder_store_root=root / ".coder",
                repo_root=root,
                run_id="run-1",
                mode="task_execution",
            ).route("Find SDK docs before editing.")
            supervisor_state = AgenticContextRouter(
                coder_store_root=root / ".coder",
                repo_root=root,
                run_id="run-1",
                mode="workflow_supervisor",
            ).route("Can we finish?", task_envelope={"verification_summaries": [{"status": "pass"}]})

        self.assertEqual(code_state.initial_source, "native_repo")
        self.assertEqual(roadmap_state.initial_source, "hybrid_rag")
        self.assertEqual(task_state.initial_source, "native_repo")
        self.assertEqual(supervisor_state.initial_source, "run_evidence")

    def test_freeze_evidence_kinds_and_packet_separation(self) -> None:
        with _repo() as root:
            (root / "src" / "app.py").write_text("def app_entry():\n    return 1\n", encoding="utf-8")
            service = NativeRepoContextService(coder_store_root=root / ".coder", repo_root=root, run_id="run-1")
            snippet, ref = service.read_file_range("src/app.py")
            rag_meta = rag_evidence_metadata("PlannerTaskState is in src/app.py")
            packet = build_harness_context_packet(
                mode="task_execution",
                user_goal="Use context.",
                workflow_id="workflow",
                agent_id="executor",
                task_envelope={"round": 1, "work_item_id": "work", "task_summary": "Use context.", "planner_order_ref": "order"},
                repo_evidence=[{"ref_id": ref.ref_id, "kind": "repo_read", "evidence_kind": "repo_evidence", "path": snippet.path}],
                run_evidence=[{"ref_id": "run-ref", "source": "verification", "evidence_kind": "run_evidence", "summary": "pass"}],
                knowledge_hints=[{"id": "hint-1", "summary": "Old note.", **rag_meta}],
                repo_evidence_refs=[ref.ref_id],
                run_evidence_refs=["run-ref"],
            )

        self.assertEqual(rag_meta["evidence_kind"], "knowledge_hint")
        self.assertFalse(code_fact_supported_by_evidence_kind("knowledge_hint"))
        self.assertTrue(code_fact_supported_by_evidence_kind("repo_evidence"))
        self.assertEqual(packet["warm"]["repo_evidence"][0]["evidence_kind"], "repo_evidence")
        self.assertEqual(packet["warm"]["run_evidence"][0]["evidence_kind"], "run_evidence")
        self.assertEqual(packet["warm"]["knowledge_hints"][0]["evidence_kind"], "knowledge_hint")

    def test_freeze_tool_schemas_and_path_safety(self) -> None:
        for action_type in (CoderRepoFindFilesAction, CoderRepoSearchTextAction, CoderRepoReadFileAction):
            schema = action_type.model_json_schema()
            self.assertNotIn("repo_root", schema["properties"])
            self.assertNotIn("run_id", schema["properties"])
            self.assertNotIn("scope_paths", schema["properties"])
        with _repo() as root:
            (root / ".env").write_text("SECRET=value\n", encoding="utf-8")
            reader = RepoReadService(repo_root=root)
            with self.assertRaises(ValueError):
                reader.read_file_range("../outside.txt")
            with self.assertRaises(ValueError):
                reader.read_file_range(".env")


class _repo:
    def __enter__(self) -> Path:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "src").mkdir()
        (root / ".coder").mkdir()
        return root

    def __exit__(self, *_args: object) -> None:
        self.tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
