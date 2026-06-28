from __future__ import annotations

import tempfile
import unittest

from fastapi.testclient import TestClient

from coder_workbench.core import (
    AgentWorkflowSpec,
    compile_runtime_profiles,
    default_planner_led_agent_workflow,
    role_card_catalog,
    validate_agent_workflow_payload,
)
from coder_workbench.agent_model.profile import AgentRuntimeProfile as InternalAgentRuntimeProfile
from coder_workbench.server.app import create_app


class AgentArchetypeTests(unittest.TestCase):
    def test_role_card_catalog_contains_ordinary_user_choices(self) -> None:
        labels = {card["label"] for card in role_card_catalog()}

        self.assertEqual(labels, {"Executor"})

    def test_role_card_payload_compiles_default_role_and_capabilities(self) -> None:
        payload = default_planner_led_agent_workflow().model_dump(mode="json", by_alias=True)
        payload["agents"][1] = {
            "id": "executor",
            "name": "Executor",
            "role_card": "executor",
            "model_tier": "standard",
            "can_talk_to_human": False,
        }

        spec = AgentWorkflowSpec.model_validate(payload)
        validation = validate_agent_workflow_payload(payload)

        self.assertEqual(validation.status, "pass")
        self.assertEqual(spec.agents[1].role, "executor")
        self.assertEqual(
            spec.agents[1].capabilities,
            ["follow_planner_order", "modify_files", "optional_check_command", "return_execution_result"],
        )

    def test_runtime_profile_compiles_runtime_managed_internals(self) -> None:
        payload = default_planner_led_agent_workflow().model_dump(mode="json", by_alias=True)
        payload["agents"][1]["role_card"] = "executor"
        workflow = AgentWorkflowSpec.model_validate(payload)

        profiles = compile_runtime_profiles(workflow)
        executor = next(profile for profile in profiles if profile.agent_id == "executor")

        self.assertIsInstance(executor, InternalAgentRuntimeProfile)
        self.assertEqual(executor.agent_archetype, "executor")
        self.assertEqual(executor.harness_id, "code-worker-harness")
        self.assertEqual(executor.authority.authority, "executor")
        self.assertTrue(executor.tool_policy["edit_files"])
        self.assertTrue(executor.token_budget["managed_by_runtime"])
        self.assertEqual(executor.internal_loops["schema_repair_attempts"], 1)


class AgentArchetypeApiTests(unittest.TestCase):
    def test_role_cards_and_runtime_profiles_api(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = TestClient(create_app(store_root=tmp, frontend_dist=tmp))
            role_cards = client.get("/api/v2/agent-role-cards")

            self.assertEqual(role_cards.status_code, 200)
            self.assertEqual(len(role_cards.json()["role_cards"]), 1)

            payload = default_planner_led_agent_workflow().model_dump(mode="json", by_alias=True)
            payload["agents"][1]["role_card"] = "executor"
            profiles = client.post("/api/v2/agent-workflows/runtime-profiles", json=payload)

        self.assertEqual(profiles.status_code, 200)
        executor = next(profile for profile in profiles.json()["profiles"] if profile["agent_id"] == "executor")
        self.assertEqual(executor["agent_archetype"], "executor")
        self.assertEqual(executor["harness_id"], "code-worker-harness")
        self.assertEqual(executor["tool_policy"]["connector_operations"], "deny_by_default")


if __name__ == "__main__":
    unittest.main()
