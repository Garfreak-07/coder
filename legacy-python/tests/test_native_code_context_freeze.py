from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from coder_workbench.context import build_harness_context_packet
from coder_workbench.context.evidence_policy import code_fact_supported_by_evidence_kind
from coder_workbench.context.repo_context_service import NativeRepoContextService
from coder_workbench.context.repo_read import RepoReadService
from coder_workbench.context.retrieval_router import ContextRetrievalRouter
from coder_workbench.memory.bm25_index import BM25Index
from coder_workbench.memory.hybrid_retriever import HybridRagRetriever
from coder_workbench.memory.models import KnowledgeChunk, MemoryAcl, MemoryRecord
from coder_workbench.memory.rag_models import HybridRagRequest
from coder_workbench.memory.store import AgentScopedMemoryStore, KnowledgeStore
from coder_workbench.openhands_tools.repo_context import (
    CoderRepoFindFilesAction,
    CoderRepoReadFileAction,
    CoderRepoSearchTextAction,
)


class NativeCodeContextFreezeTests(unittest.TestCase):
    def test_code_like_query_routes_to_repo_search_not_rag_only(self) -> None:
        decision = ContextRetrievalRouter().decide("Where is PlannerTaskState defined?")

        self.assertTrue(decision.use_repo_search)
        self.assertFalse(decision.use_rag)

    def test_design_query_may_route_to_rag(self) -> None:
        decision = ContextRetrievalRouter().decide("What is the roadmap decision for Obsidian notes?")

        self.assertTrue(decision.use_rag)
        self.assertTrue(decision.rag_is_hint_only)

    def test_rag_result_is_marked_knowledge_hint(self) -> None:
        with _stores() as stores:
            memory_store, knowledge_store, root = stores
            chunk = knowledge_store.append_chunk(_chunk("chunk-1", text="Function PlannerTaskState controls readiness."))
            BM25Index(root).rebuild(memory_records=[], knowledge_chunks=[chunk])

            result = HybridRagRetriever(
                memory_store=memory_store,
                knowledge_store=knowledge_store,
                bm25_index=BM25Index(root),
            ).retrieve(_rag_request(query="PlannerTaskState readiness"))[0]

            self.assertEqual(result.evidence_kind, "knowledge_hint")
            self.assertTrue(result.requires_repo_verification)
            self.assertFalse(code_fact_supported_by_evidence_kind(result.evidence_kind))

    def test_native_repo_read_result_is_repo_evidence(self) -> None:
        with _repo() as data:
            root, coder_root = data
            (root / "src" / "app.py").write_text("def target():\n    return 1\n", encoding="utf-8")
            service = NativeRepoContextService(coder_store_root=coder_root, repo_root=root, run_id="run-1")

            _snippet, ref = service.read_file_range("src/app.py")
            payload = service.read_evidence(ref.ref_id)

            self.assertEqual(payload["evidence_kind"], "repo_evidence")
            self.assertTrue(code_fact_supported_by_evidence_kind(payload["evidence_kind"]))

    def test_repo_tool_schemas_do_not_expose_bound_params(self) -> None:
        for action_type in (CoderRepoFindFilesAction, CoderRepoSearchTextAction, CoderRepoReadFileAction):
            with self.subTest(action_type=action_type.__name__):
                schema = action_type.model_json_schema()
                self.assertNotIn("repo_root", schema["properties"])
                self.assertNotIn("run_id", schema["properties"])
                self.assertNotIn("scope_paths", schema["properties"])

    def test_path_traversal_and_env_are_rejected(self) -> None:
        with _repo() as data:
            root, _coder_root = data
            (root / ".env").write_text("SECRET=value\n", encoding="utf-8")
            reader = RepoReadService(repo_root=root)

            with self.assertRaises(ValueError):
                reader.read_file_range("../outside.txt")
            with self.assertRaises(ValueError):
                reader.read_file_range(".env")

    def test_context_packet_separates_repo_evidence_and_knowledge_hints(self) -> None:
        packet = build_harness_context_packet(
            mode="task_execution",
            user_goal="Use context.",
            workflow_id="workflow",
            agent_id="executor",
            task_envelope={"round": 1, "work_item_id": "work", "task_summary": "Use context.", "planner_order_ref": "order"},
            repo_evidence=[{"ref_id": "repo-read:1", "kind": "repo_read", "evidence_kind": "repo_evidence"}],
            knowledge_hints=[{"id": "hint-1", "summary": "Old note.", "evidence_kind": "knowledge_hint"}],
        )

        self.assertEqual(packet["warm"]["repo_evidence"][0]["evidence_kind"], "repo_evidence")
        self.assertEqual(packet["warm"]["knowledge_hints"][0]["evidence_kind"], "knowledge_hint")

    def test_task_execution_cannot_retrieve_user_or_persona_memory_through_rag(self) -> None:
        with _stores() as stores:
            memory_store, knowledge_store, root = stores
            user_record = memory_store.append_record(
                _record(
                    "user-1",
                    scope="user",
                    source_type="user_memory",
                    purpose=["coding_knowledge"],
                    acl=MemoryAcl(allowed_agents=["planning_chat"], allowed_contexts=["assistant_message"]),
                )
            )
            persona_record = memory_store.append_record(
                _record(
                    "style-1",
                    scope="agent_style",
                    source_type="agent_style",
                    purpose=["persona_style"],
                    acl=MemoryAcl(allowed_agents=["planning_chat"], allowed_contexts=["assistant_message"]),
                )
            )
            BM25Index(root).rebuild(memory_records=[user_record, persona_record], knowledge_chunks=[])

            results = HybridRagRetriever(
                memory_store=memory_store,
                knowledge_store=knowledge_store,
                bm25_index=BM25Index(root),
            ).retrieve(_rag_request(query="coding concise", role="task_execution", requested_context="execution_prompt"))

            self.assertEqual(results, [])

    def test_existing_hybrid_rag_still_returns_acl_allowed_knowledge(self) -> None:
        with _stores() as stores:
            memory_store, knowledge_store, root = stores
            chunk = knowledge_store.append_chunk(_chunk("chunk-1", text="Use apply_patch for code edits."))
            BM25Index(root).rebuild(memory_records=[], knowledge_chunks=[chunk])

            results = HybridRagRetriever(
                memory_store=memory_store,
                knowledge_store=knowledge_store,
                bm25_index=BM25Index(root),
            ).retrieve(_rag_request(query="apply_patch edits"))

            self.assertEqual([result.id for result in results], ["chunk-1"])


class _repo:
    def __enter__(self) -> tuple[Path, Path]:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "src").mkdir()
        coder_root = root / ".coder"
        coder_root.mkdir()
        return root, coder_root

    def __exit__(self, *_args: object) -> None:
        self.tmp.cleanup()


class _stores:
    def __enter__(self) -> tuple[AgentScopedMemoryStore, KnowledgeStore, Path]:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name) / ".coder"
        return AgentScopedMemoryStore(root), KnowledgeStore(root), root

    def __exit__(self, *_args: object) -> None:
        self.tmp.cleanup()


def _rag_request(**overrides) -> HybridRagRequest:
    values = {
        "role": "task_execution",
        "requested_context": "execution_prompt",
        "query": "query",
        "project_id": "project",
    }
    values.update(overrides)
    return HybridRagRequest(**values)


def _chunk(chunk_id: str, *, text: str) -> KnowledgeChunk:
    return KnowledgeChunk(
        chunk_id=chunk_id,
        source_id="source-1",
        title=f"Chunk {chunk_id}",
        text=text,
        summary=text[:120],
        purpose=["coding_knowledge"],
        acl=MemoryAcl(
            allowed_agents=["planning_chat", "workflow_supervisor", "task_execution"],
            allowed_contexts=["assistant_message", "workflow_supervision", "execution_prompt"],
        ),
        content_hash=f"sha256:{chunk_id}",
        token_estimate=20,
    )


def _record(record_id: str, **overrides) -> MemoryRecord:
    values = {
        "id": record_id,
        "scope": "project",
        "source_type": "project_memory",
        "purpose": ["planning_context"],
        "title": "Project memory",
        "summary": "Planner memory.",
        "project_id": "project",
        "acl": MemoryAcl(allowed_agents=["planning_chat"], allowed_contexts=["assistant_message"]),
        "trust_level": "user_confirmed",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "token_estimate": 20,
    }
    values.update(overrides)
    return MemoryRecord(**values)


if __name__ == "__main__":
    unittest.main()
