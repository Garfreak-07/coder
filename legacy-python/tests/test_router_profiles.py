from __future__ import annotations

import unittest

from coder_workbench.context.router_profiles import router_profile_for_mode


class RouterProfilesTests(unittest.TestCase):
    def test_profiles_exist_for_all_router_modes(self) -> None:
        self.assertEqual(router_profile_for_mode("planning_chat").role, "planning_chat")
        self.assertEqual(router_profile_for_mode("workflow_supervisor").role, "workflow_supervisor")
        self.assertEqual(router_profile_for_mode("task_execution").role, "task_execution")

    def test_task_execution_never_rag_first_or_user_memory(self) -> None:
        profile = router_profile_for_mode("task_execution")

        self.assertFalse(profile.rag_first_allowed)
        self.assertFalse(profile.can_ask_user)
        self.assertNotIn("user", profile.allowed_memory_scopes)
        self.assertNotIn("agent_style", profile.allowed_memory_scopes)

    def test_planning_chat_can_ask_user(self) -> None:
        self.assertTrue(router_profile_for_mode("planning_chat").can_ask_user)

    def test_workflow_supervisor_cannot_ask_user(self) -> None:
        self.assertFalse(router_profile_for_mode("workflow_supervisor").can_ask_user)

    def test_unknown_mode_rejected(self) -> None:
        with self.assertRaises(ValueError):
            router_profile_for_mode("unknown")


if __name__ == "__main__":
    unittest.main()
