from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from coder_workbench.memory.bm25_index import BM25Index
from coder_workbench.memory.models import KnowledgeChunk, MemoryAcl, MemoryRecord
from coder_workbench.memory.store import AgentScopedMemoryStore, KnowledgeStore
from coder_workbench.openhands_tools.hybrid_rag_search import (
    CoderHybridRagSearchAction,
    CoderHybridRagSearchObservation,
    CoderHybridRagSearchTool,
)
from openhands.sdk.tool import list_registered_tools


class OpenHandsHybridRagToolTests(unittest.TestCase):
    def test_tool_registers(self) -> None:
        self.assertIn(CoderHybridRagSearchTool.name, list_registered_tools())

    def test_create_requires_bound_runtime_params(self) -> None:
        with self.assertRaises(KeyError):
            CoderHybridRagSearchTool.create(conv_state=None)

    def test_action_schema_excludes_role_and_context(self) -> None:
        schema = CoderHybridRagSearchAction.model_json_schema()

        self.assertNotIn("role", schema["properties"])
        self.assertNotIn("requested_context", schema["properties"])
        self.assertNotIn("memory_root", schema["properties"])
        with self.assertRaises(ValidationError):
            CoderHybridRagSearchAction.model_validate(
                {"query": "test", "role": "task_execution", "requested_context": "execution_prompt"}
            )

    def test_planning_chat_tool_can_retrieve_allowed_project_memory(self) -> None:
        with _indexed_store() as data:
            memory_store, _knowledge_store, root = data
            record = memory_store.append_record(
                _record(
                    "project-1",
                    purpose=["planning_context"],
                    summary="Planner should use the existing workflow.",
                    acl=MemoryAcl(allowed_agents=["planning_chat"], allowed_contexts=["assistant_message"]),
                )
            )
            BM25Index(root).rebuild(memory_records=[record], knowledge_chunks=[])
            tool = CoderHybridRagSearchTool.create(
                conv_state=None,
                memory_root=str(root),
                role="planning_chat",
                requested_context="assistant_message",
                project_id="project",
                max_tokens=1000,
            )[0]

            observation = tool(CoderHybridRagSearchAction(query="existing workflow"))

            self.assertEqual(observation.returned, 1)
            self.assertEqual(observation.results[0]["id"], "project-1")

    def test_task_execution_tool_cannot_retrieve_persona_memory(self) -> None:
        with _indexed_store() as data:
            memory_store, _knowledge_store, root = data
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
            BM25Index(root).rebuild(memory_records=[record], knowledge_chunks=[])
            tool = CoderHybridRagSearchTool.create(
                conv_state=None,
                memory_root=str(root),
                role="task_execution",
                requested_context="execution_prompt",
                project_id="project",
                max_tokens=1000,
            )[0]

            observation = tool(CoderHybridRagSearchAction(query="concise wording"))

            self.assertEqual(observation.returned, 0)

    def test_observation_to_llm_content_is_compact(self) -> None:
        observation = CoderHybridRagSearchObservation(
            query="query",
            returned=1,
            token_estimate=10,
            cold_refs=["source-1"],
            results=[
                {
                    "id": "chunk-1",
                    "title": "Chunk",
                    "summary": "Short summary.",
                    "fusion_score": 0.1,
                    "dense_rank": None,
                    "bm25_rank": 1,
                    "source_refs": [{"ref": "source-1"}],
                }
            ],
        )

        text = "".join(part.text for part in observation.to_llm_content)

        self.assertIn("Hybrid RAG returned 1 results.", text)
        self.assertIn("Summary: Short summary.", text)
        self.assertLess(len(text), 1000)

    def test_include_content_returns_bounded_preview_only(self) -> None:
        with _indexed_store() as data:
            _memory_store, knowledge_store, root = data
            chunk = knowledge_store.append_chunk(_chunk("chunk-1", text="preview " * 200))
            BM25Index(root).rebuild(memory_records=[], knowledge_chunks=[chunk])
            tool = CoderHybridRagSearchTool.create(
                conv_state=None,
                memory_root=str(root),
                role="task_execution",
                requested_context="execution_prompt",
                project_id="project",
                max_tokens=1000,
            )[0]

            observation = tool(CoderHybridRagSearchAction(query="preview", include_content=True))

            self.assertLessEqual(len(observation.results[0]["text_preview"]), 500)

    def test_rag_results_are_labeled_as_knowledge_hints(self) -> None:
        with _indexed_store() as data:
            _memory_store, knowledge_store, root = data
            chunk = knowledge_store.append_chunk(_chunk("chunk-1", text="Function PlannerTaskState controls readiness."))
            BM25Index(root).rebuild(memory_records=[], knowledge_chunks=[chunk])
            tool = CoderHybridRagSearchTool.create(
                conv_state=None,
                memory_root=str(root),
                role="task_execution",
                requested_context="execution_prompt",
                project_id="project",
                max_tokens=1000,
            )[0]

            observation = tool(CoderHybridRagSearchAction(query="PlannerTaskState readiness"))
            text = "".join(part.text for part in observation.to_llm_content)

            self.assertEqual(observation.results[0]["evidence_kind"], "knowledge_hint")
            self.assertTrue(observation.results[0]["requires_repo_verification"])
            self.assertIn("Requires repo verification: true", text)
            self.assertIn("Verify code claims with repo search/read", text)

    def test_annotations_mark_tool_read_only(self) -> None:
        tool = CoderHybridRagSearchTool.create(
            conv_state=None,
            memory_root=".",
            role="task_execution",
            requested_context="execution_prompt",
            project_id=None,
        )[0]

        self.assertTrue(tool.annotations.readOnlyHint)
        self.assertFalse(tool.annotations.destructiveHint)
        self.assertFalse(tool.annotations.openWorldHint)


class _indexed_store:
    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / ".coder"
        self.memory_store = AgentScopedMemoryStore(self.root)
        self.knowledge_store = KnowledgeStore(self.root)
        return self.memory_store, self.knowledge_store, self.root

    def __exit__(self, *_args):
        self.tmp.cleanup()


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
        "acl": MemoryAcl(allowed_agents=["planning_chat"], allowed_contexts=["assistant_message"]),
        "trust_level": "user_confirmed",
        "created_at": _now(),
        "updated_at": _now(),
        "token_estimate": 20,
    }
    values.update(overrides)
    return MemoryRecord(**values)


def _chunk(chunk_id: str, *, text: str) -> KnowledgeChunk:
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
        token_estimate=20,
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    unittest.main()
