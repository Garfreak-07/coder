from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from coder_workbench.context.agentic_router import AgenticContextRouter
from coder_workbench.memory.rag_models import HybridRagResult


class AgenticContextRouterTests(unittest.TestCase):
    def test_code_like_query_starts_with_native_repo(self) -> None:
        with _repo() as root:
            (root / "src" / "app.py").write_text("class PlannerTaskState:\n    pass\n", encoding="utf-8")

            state = _router(root, mode="planning_chat").route("Where is PlannerTaskState defined?")

        self.assertEqual(state.initial_source, "native_repo")
        self.assertTrue(state.repo_evidence)
        self.assertTrue(any(item["step"] == "classify_intent" for item in state.route_trace))

    def test_planning_history_query_may_start_with_rag(self) -> None:
        with _repo() as root:
            state = _router(root, mode="planning_chat", hybrid=FakeHybrid()).route(
                "What roadmap decision did we make for Obsidian notes?"
            )

        self.assertEqual(state.initial_source, "hybrid_rag")
        self.assertEqual(state.knowledge_hints[0]["evidence_kind"], "knowledge_hint")

    def test_task_execution_never_starts_rag_first(self) -> None:
        with _repo() as root:
            state = _router(root, mode="task_execution", hybrid=FakeHybrid()).route("Find SDK docs for this edit.")

        self.assertEqual(state.initial_source, "native_repo")

    def test_workflow_supervisor_prefers_run_evidence(self) -> None:
        with _repo() as root:
            state = _router(root, mode="workflow_supervisor").route(
                "Decide whether to finish.",
                task_envelope={
                    "execution_results": [{"status": "completed", "summary": "Tests passed."}],
                    "verification_summaries": [{"status": "pass", "evidence_refs": ["check-ref"]}],
                    "evidence_refs": ["execution-ref"],
                },
            )

        self.assertEqual(state.initial_source, "run_evidence")
        self.assertTrue(state.run_evidence)
        self.assertIn("execution-ref", state.run_evidence_refs)

    def test_weak_repo_result_can_switch_to_rag_for_conceptual_query(self) -> None:
        with _repo() as root:
            state = _router(root, mode="planning_chat", hybrid=FakeHybrid()).route(
                "Where is MissingSymbol and what roadmap decision did we make?"
            )

        self.assertEqual(state.initial_source, "native_repo")
        self.assertTrue(any(item["step"] == "switch_source" and item["source"] == "hybrid_rag" for item in state.route_trace))
        self.assertTrue(state.knowledge_hints)

    def test_rag_code_like_result_requires_repo_verification(self) -> None:
        with _repo() as root:
            (root / "src" / "app.py").write_text("class PlannerTaskState:\n    pass\n", encoding="utf-8")

            state = _router(root, mode="planning_chat", hybrid=FakeHybrid(code_like=True)).route(
                "Find external documentation for provider usage."
            )

        self.assertTrue(state.requires_repo_verification)
        self.assertTrue(state.knowledge_hints[0]["requires_repo_verification"])
        self.assertTrue(state.repo_evidence)

    def test_max_iterations_is_enforced(self) -> None:
        with _repo() as root:
            state = _router(root, mode="planning_chat").route("What roadmap decision did we make?")

        self.assertLessEqual(state.iterations, state.max_iterations)


class FakeHybrid:
    def __init__(self, *, code_like: bool = False) -> None:
        self.code_like = code_like

    def retrieve(self, _request: Any) -> list[HybridRagResult]:
        summary = "PlannerTaskState is in src/app.py" if self.code_like else "Use the Obsidian roadmap decision."
        return [
            HybridRagResult(
                id="hint-1",
                item_type="knowledge_chunk",
                title="Routing note",
                summary=summary,
                scope="knowledge_source",
                purpose=["coding_knowledge"],
                fusion_score=1.0,
                token_estimate=10,
                requires_repo_verification=self.code_like,
            )
        ]


class _repo:
    def __enter__(self) -> Path:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "src").mkdir()
        (root / ".coder").mkdir()
        return root

    def __exit__(self, *_args: object) -> None:
        self.tmp.cleanup()


def _router(root: Path, *, mode: str, hybrid: Any | None = None) -> AgenticContextRouter:
    return AgenticContextRouter(
        coder_store_root=root / ".coder",
        repo_root=root,
        run_id="run-1",
        mode=mode,  # type: ignore[arg-type]
        hybrid_retriever=hybrid,
    )


if __name__ == "__main__":
    unittest.main()
