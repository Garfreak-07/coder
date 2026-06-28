from __future__ import annotations

import unittest

from pydantic import ValidationError

from coder_workbench.context.router_models import (
    AgenticContextRouterState,
    ContextRetrievalDecision,
    RetrievalIntent,
    RouterRoleProfile,
)


class RouterModelsTests(unittest.TestCase):
    def test_retrieval_intent_rejects_unknown_extra_fields(self) -> None:
        with self.assertRaises(ValidationError):
            RetrievalIntent.model_validate({"intent_type": "code_fact", "unexpected": True})

    def test_agentic_router_state_defaults_are_bounded(self) -> None:
        state = AgenticContextRouterState(mode="task_execution", query="Edit src/app.py")

        self.assertEqual(state.selected_source, "none")
        self.assertEqual(state.max_iterations, 3)
        self.assertEqual(state.route_trace, [])

    def test_context_retrieval_decision_uses_hint_only_rag_default(self) -> None:
        decision = ContextRetrievalDecision(reason="test")

        self.assertTrue(decision.rag_is_hint_only)
        self.assertEqual(decision.initial_source, "none")

    def test_role_profile_rejects_unknown_extra_fields(self) -> None:
        with self.assertRaises(ValidationError):
            RouterRoleProfile.model_validate(
                {
                    "role": "planning_chat",
                    "default_sources": ["hybrid_rag"],
                    "allowed_sources": ["hybrid_rag"],
                    "allowed_memory_scopes": ["project"],
                    "allowed_contexts": ["assistant_message"],
                    "rag_first_allowed": True,
                    "repo_verification_required_for_code_claims": True,
                    "can_ask_user": True,
                    "can_write_files": False,
                    "can_run_commands": False,
                    "max_repo_evidence_tokens": 1,
                    "max_run_evidence_tokens": 1,
                    "max_rag_hint_tokens": 1,
                    "extra": "blocked",
                }
            )


if __name__ == "__main__":
    unittest.main()
