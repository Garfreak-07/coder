from __future__ import annotations

import unittest

from coder_workbench.context.retrieval_router import ContextRetrievalRouter, RetrievalIntent


class ContextRetrievalRouterTests(unittest.TestCase):
    def test_function_name_routes_to_repo_search(self) -> None:
        decision = ContextRetrievalRouter().decide("Where is PlannerTaskState defined?")

        self.assertTrue(decision.use_repo_discovery)
        self.assertTrue(decision.use_repo_search)
        self.assertFalse(decision.use_rag)

    def test_file_path_routes_to_repo_read_and_search(self) -> None:
        decision = ContextRetrievalRouter().decide("What does src/coder_workbench/context/harness_packets.py contain?")

        self.assertTrue(decision.use_repo_search)
        self.assertTrue(decision.use_repo_read)

    def test_design_decision_routes_to_rag(self) -> None:
        decision = ContextRetrievalRouter().decide("Why did we choose the planner-led workflow design?")

        self.assertFalse(decision.use_repo_search)
        self.assertTrue(decision.use_rag)
        self.assertTrue(decision.rag_is_hint_only)

    def test_external_api_docs_route_to_rag(self) -> None:
        decision = ContextRetrievalRouter().decide("Find SDK docs for the provider API.")

        self.assertTrue(decision.use_rag)

    def test_code_like_rag_hint_requires_repo_verification(self) -> None:
        decision = ContextRetrievalRouter().decide(
            intent=RetrievalIntent(
                needs_external_docs=True,
                query_is_code_like=True,
                needs_code_fact=True,
            )
        )

        self.assertTrue(decision.use_rag)
        self.assertTrue(decision.requires_repo_verification)

    def test_executor_mode_defaults_to_repo_native_first(self) -> None:
        decision = ContextRetrievalRouter().decide("Implement the work item.", mode="task_execution")

        self.assertTrue(decision.use_repo_discovery)
        self.assertTrue(decision.use_repo_search)

    def test_planning_chat_roadmap_may_use_rag(self) -> None:
        decision = ContextRetrievalRouter().decide("What is the roadmap for Obsidian notes?", mode="planning_chat")

        self.assertTrue(decision.use_rag)
        self.assertFalse(decision.use_repo_read)


if __name__ == "__main__":
    unittest.main()
