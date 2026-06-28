from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from coder_workbench.memory.bm25_index import BM25Index
from coder_workbench.memory.hybrid_retriever import HybridRagRetriever, weighted_rrf
from coder_workbench.memory.models import KnowledgeChunk, MemoryAcl, MemoryRecord
from coder_workbench.memory.policy import TASK_EXECUTION_MEMORY_POLICY
from coder_workbench.memory.rag_models import HybridRagRequest, RetrievalHit
from coder_workbench.memory.store import AgentScopedMemoryStore, KnowledgeStore


class HybridRagRetrieverTests(unittest.TestCase):
    def test_weighted_rrf_ranks_duplicate_highest(self) -> None:
        dense = [
            RetrievalHit(id="A", item_type="knowledge_chunk", rank=1, score=0.9, channel="dense"),
            RetrievalHit(id="B", item_type="knowledge_chunk", rank=2, score=0.8, channel="dense"),
        ]
        bm25 = [
            RetrievalHit(id="B", item_type="knowledge_chunk", rank=1, score=10.0, channel="bm25"),
            RetrievalHit(id="C", item_type="knowledge_chunk", rank=2, score=8.0, channel="bm25"),
        ]

        fused = weighted_rrf(dense, bm25, dense_weight=0.55, bm25_weight=0.45)

        self.assertEqual(fused[0][0], "B")
        self.assertEqual(len([item for item in fused if item[0] == "B"]), 1)

    def test_dense_only_retrieval_works(self) -> None:
        with _stores() as stores:
            memory_store, knowledge_store, _root = stores
            knowledge_store.append_chunk(_chunk("chunk-1", text="Dense search knowledge."))

            results = HybridRagRetriever(
                memory_store=memory_store,
                knowledge_store=knowledge_store,
                chroma_index=_DenseStub("chunk-1"),
            ).retrieve(_request(query="semantic knowledge"))

            self.assertEqual([result.id for result in results], ["chunk-1"])
            self.assertEqual(results[0].dense_rank, 1)

    def test_bm25_only_retrieval_works(self) -> None:
        with _stores() as stores:
            memory_store, knowledge_store, root = stores
            chunk = knowledge_store.append_chunk(_chunk("chunk-1", text="Function PlannerTaskState controls readiness."))
            index = BM25Index(root)
            index.rebuild(memory_records=[], knowledge_chunks=[chunk])

            results = HybridRagRetriever(
                memory_store=memory_store,
                knowledge_store=knowledge_store,
                bm25_index=index,
            ).retrieve(_request(query="PlannerTaskState readiness"))

            self.assertEqual([result.id for result in results], ["chunk-1"])
            self.assertEqual(results[0].bm25_rank, 1)
            self.assertEqual(results[0].evidence_kind, "knowledge_hint")
            self.assertTrue(results[0].requires_repo_verification)

    def test_both_missing_falls_back_to_memory_retriever(self) -> None:
        with _stores() as stores:
            memory_store, knowledge_store, _root = stores
            knowledge_store.append_chunk(_chunk("chunk-1", text="Use apply_patch for edits."))

            results = HybridRagRetriever(
                memory_store=memory_store,
                knowledge_store=knowledge_store,
            ).retrieve(_request(query="apply_patch edits"))

            self.assertEqual(results[0].id, "chunk-1")
            self.assertEqual(results[0].metadata["fallback"], "memory_retriever")

    def test_task_execution_cannot_retrieve_user_memory(self) -> None:
        with _stores() as stores:
            memory_store, knowledge_store, root = stores
            record = memory_store.append_record(
                _record(
                    "user-1",
                    scope="user",
                    source_type="user_memory",
                    purpose=["coding_knowledge"],
                    summary="User preference about coding.",
                    acl=MemoryAcl(allowed_agents=["planning_chat"], allowed_contexts=["assistant_message"]),
                )
            )
            index = BM25Index(root)
            index.rebuild(memory_records=[record], knowledge_chunks=[])

            results = HybridRagRetriever(
                memory_store=memory_store,
                knowledge_store=knowledge_store,
                bm25_index=index,
            ).retrieve(_request(query="coding preference", role="task_execution", requested_context="execution_prompt"))

            self.assertEqual(results, [])

    def test_task_execution_cannot_retrieve_persona_style(self) -> None:
        with _stores() as stores:
            memory_store, knowledge_store, root = stores
            record = memory_store.append_record(
                _record(
                    "style-1",
                    scope="agent_style",
                    source_type="agent_style",
                    purpose=["persona_style"],
                    summary="Use concise wording.",
                    acl=MemoryAcl(allowed_agents=["planning_chat"], allowed_contexts=["assistant_message"]),
                )
            )
            index = BM25Index(root)
            index.rebuild(memory_records=[record], knowledge_chunks=[])

            results = HybridRagRetriever(
                memory_store=memory_store,
                knowledge_store=knowledge_store,
                bm25_index=index,
            ).retrieve(_request(query="concise wording", role="task_execution", requested_context="execution_prompt"))

            self.assertEqual(results, [])

    def test_workflow_supervisor_cannot_retrieve_persona_style(self) -> None:
        with _stores() as stores:
            memory_store, knowledge_store, root = stores
            record = memory_store.append_record(
                _record(
                    "style-1",
                    scope="agent_style",
                    source_type="agent_style",
                    purpose=["persona_style"],
                    summary="Use concise wording.",
                    acl=MemoryAcl(allowed_agents=["planning_chat"], allowed_contexts=["assistant_message"]),
                )
            )
            index = BM25Index(root)
            index.rebuild(memory_records=[record], knowledge_chunks=[])

            results = HybridRagRetriever(
                memory_store=memory_store,
                knowledge_store=knowledge_store,
                bm25_index=index,
            ).retrieve(_request(query="concise wording", role="workflow_supervisor", requested_context="workflow_supervision"))

            self.assertEqual(results, [])

    def test_planning_chat_can_retrieve_persona_style_for_assistant_message(self) -> None:
        with _stores() as stores:
            memory_store, knowledge_store, root = stores
            record = memory_store.append_record(
                _record(
                    "style-1",
                    scope="agent_style",
                    source_type="agent_style",
                    purpose=["persona_style"],
                    summary="Use concise wording.",
                    acl=MemoryAcl(allowed_agents=["planning_chat"], allowed_contexts=["assistant_message"]),
                )
            )
            index = BM25Index(root)
            index.rebuild(memory_records=[record], knowledge_chunks=[])

            results = HybridRagRetriever(
                memory_store=memory_store,
                knowledge_store=knowledge_store,
                bm25_index=index,
            ).retrieve(_request(query="concise wording", role="planning_chat", requested_context="assistant_message"))

            self.assertEqual([result.id for result in results], ["style-1"])

    def test_top_k_is_enforced(self) -> None:
        with _stores() as stores:
            memory_store, knowledge_store, root = stores
            chunks = [
                knowledge_store.append_chunk(_chunk("chunk-1", text="shared query first")),
                knowledge_store.append_chunk(_chunk("chunk-2", text="shared query second")),
            ]
            index = BM25Index(root)
            index.rebuild(memory_records=[], knowledge_chunks=chunks)

            results = HybridRagRetriever(
                memory_store=memory_store,
                knowledge_store=knowledge_store,
                bm25_index=index,
            ).retrieve(_request(query="shared query", top_k=1))

            self.assertEqual(len(results), 1)

    def test_token_budget_is_enforced(self) -> None:
        with _stores() as stores:
            memory_store, knowledge_store, root = stores
            chunks = [
                knowledge_store.append_chunk(_chunk("large", text="budget query large", token_estimate=500)),
                knowledge_store.append_chunk(_chunk("small", text="budget query small", token_estimate=20)),
            ]
            index = BM25Index(root)
            index.rebuild(memory_records=[], knowledge_chunks=chunks)
            policy = TASK_EXECUTION_MEMORY_POLICY.model_copy(update={"max_tokens": 50, "max_records": 10})

            results = HybridRagRetriever(
                memory_store=memory_store,
                knowledge_store=knowledge_store,
                bm25_index=index,
                policies={"task_execution": policy},
            ).retrieve(_request(query="budget query", top_k=5))

            self.assertEqual([result.id for result in results], ["small"])

    def test_include_content_false_omits_preview(self) -> None:
        with _stores() as stores:
            memory_store, knowledge_store, root = stores
            chunk = knowledge_store.append_chunk(_chunk("chunk-1", text="preview text"))
            index = BM25Index(root)
            index.rebuild(memory_records=[], knowledge_chunks=[chunk])

            result = HybridRagRetriever(
                memory_store=memory_store,
                knowledge_store=knowledge_store,
                bm25_index=index,
            ).retrieve(_request(query="preview"))[0]

            self.assertIsNone(result.text_preview)

    def test_include_content_true_returns_bounded_preview(self) -> None:
        with _stores() as stores:
            memory_store, knowledge_store, root = stores
            chunk = knowledge_store.append_chunk(_chunk("chunk-1", text="preview " * 50))
            index = BM25Index(root)
            index.rebuild(memory_records=[], knowledge_chunks=[chunk])

            result = HybridRagRetriever(
                memory_store=memory_store,
                knowledge_store=knowledge_store,
                bm25_index=index,
            ).retrieve(_request(query="preview", include_content=True, content_preview_chars=40))[0]

            self.assertLessEqual(len(result.text_preview or ""), 40)


class _stores:
    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / ".coder"
        self.memory_store = AgentScopedMemoryStore(self.root)
        self.knowledge_store = KnowledgeStore(self.root)
        return self.memory_store, self.knowledge_store, self.root

    def __exit__(self, *_args):
        self.tmp.cleanup()


class _DenseStub:
    def __init__(self, item_id: str) -> None:
        self.item_id = item_id

    def search(self, query: str, *, top_k: int, where=None):
        return [type("Hit", (), {"id": self.item_id, "rank": 1, "score": 0.9})()]


def _request(**overrides) -> HybridRagRequest:
    values = {
        "role": "task_execution",
        "requested_context": "execution_prompt",
        "query": "query",
        "project_id": "project",
    }
    values.update(overrides)
    return HybridRagRequest(**values)


def _chunk(chunk_id: str, *, text: str, token_estimate: int = 20) -> KnowledgeChunk:
    return KnowledgeChunk(
        chunk_id=chunk_id,
        source_id="source-1",
        title=f"Chunk {chunk_id}",
        text=text,
        summary=text[:120],
        tags=["rag"],
        purpose=["coding_knowledge"],
        acl=MemoryAcl(
            allowed_agents=["planning_chat", "workflow_supervisor", "task_execution"],
            allowed_contexts=["assistant_message", "workflow_supervision", "execution_prompt"],
        ),
        content_hash=f"sha256:{chunk_id}",
        token_estimate=token_estimate,
    )


def _record(record_id: str, **overrides) -> MemoryRecord:
    values = {
        "id": record_id,
        "scope": "project",
        "source_type": "project_memory",
        "purpose": ["planning_context"],
        "title": "Project memory",
        "summary": "Planner memory.",
        "content": "Small safe content.",
        "project_id": "project",
        "acl": MemoryAcl(
            allowed_agents=["planning_chat"],
            allowed_contexts=["assistant_message"],
        ),
        "trust_level": "user_confirmed",
        "created_at": _now(),
        "updated_at": _now(),
        "token_estimate": 20,
    }
    values.update(overrides)
    return MemoryRecord(**values)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    unittest.main()
