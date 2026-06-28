from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from coder_workbench.core import default_planner_led_agent_workflow
from coder_workbench.harness_runtime import HarnessRunResult
from coder_workbench.server.app import create_app


class PlannerChatSessionTests(unittest.TestCase):
    def test_create_session(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as store:
            client = TestClient(create_app(store_root=store, frontend_dist=store))

            response = client.post(
                "/api/v2/planner-chat/sessions",
                json={"workflow_id": "default-planner-led", "planner_agent_id": "planner"},
            )

        self.assertEqual(response.status_code, 200)
        session = response.json()
        self.assertTrue(session["session_id"])
        self.assertEqual(session["interaction_mode"], "discuss")
        self.assertEqual(session["status"], "chatting")
        self.assertEqual(session["task_state"]["readiness"], "not_ready")

    def test_discuss_turn_updates_task_state(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as store:
            client = TestClient(create_app(store_root=store, frontend_dist=store))
            session_id = _create_session(client)

            response = client.post(
                f"/api/v2/planner-chat/sessions/{session_id}/turn",
                json={"message": "Plan a docs update.", "interaction_mode": "discuss"},
            )
            stored = client.get(f"/api/v2/planner-chat/sessions/{session_id}").json()

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["generation"], 1)
        self.assertEqual(payload["turn"]["interaction_mode"], "discuss")
        self.assertEqual(payload["turn"]["task_state"]["readiness"], "needs_clarification")
        self.assertEqual(stored["generation"], 1)
        self.assertEqual(len(stored["messages"]), 2)

    def test_discuss_mode_never_starts_run(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as store:
            client = TestClient(create_app(store_root=store, frontend_dist=store))
            session_id = _create_session(client)

            response = client.post(
                f"/api/v2/planner-chat/sessions/{session_id}/turn",
                json={"message": "Make a plan and start it.", "interaction_mode": "discuss"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIsNone(payload["run_id"])
        self.assertNotEqual(payload["turn"]["decision"], "start_workflow")

    def test_work_mode_not_ready_returns_clarification_without_run(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as store:
            client = TestClient(create_app(store_root=store, frontend_dist=store))
            session_id = _create_session(client, interaction_mode="work")

            response = client.post(
                f"/api/v2/planner-chat/sessions/{session_id}/turn",
                json={"message": "Start.", "interaction_mode": "work"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIsNone(payload["run_id"])
        self.assertEqual(payload["turn"]["interaction_mode"], "work")
        self.assertIn(payload["turn"]["decision"], {"continue_chat", "blocked_needs_clarification"})
        self.assertTrue(payload["turn"]["task_state"]["open_questions"])

    def test_switching_discuss_to_work_preserves_task_state(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as store:
            client = TestClient(create_app(store_root=store, frontend_dist=store))
            session_id = _create_session(client)

            first = client.post(
                f"/api/v2/planner-chat/sessions/{session_id}/turn",
                json={"message": "Plan a docs update.", "interaction_mode": "discuss"},
            ).json()
            second = client.post(
                f"/api/v2/planner-chat/sessions/{session_id}/turn",
                json={"message": "Start.", "interaction_mode": "work"},
            ).json()

        self.assertEqual(first["turn"]["task_state"]["goal"], "Plan a docs update.")
        self.assertEqual(second["generation"], 2)
        self.assertEqual(second["turn"]["task_state"]["goal"], "Plan a docs update.")
        self.assertIsNone(second["run_id"])

    def test_work_mode_ready_starts_live_run(self) -> None:
        workflow = default_planner_led_agent_workflow().model_dump(mode="json", by_alias=True, exclude_none=True)

        class FakeHarnessRuntimeManager:
            def __init__(self, **_kwargs):
                pass

            def run_planning_chat(self, **_kwargs):
                return HarnessRunResult(
                    status="completed",
                    artifact_type="planner_chat_turn",
                    artifact={
                        "artifact_type": "planner_chat_turn",
                        "assistant_message": "I have enough detail and will start the workflow.",
                        "interaction_mode": "work",
                        "decision": "start_workflow",
                        "visible_thinking": {"phase": "ready_to_start", "summary": "Ready to start."},
                        "task_state": {
                            "goal": "Run ready workflow.",
                            "scope": [],
                            "success_criteria": ["The workflow starts."],
                            "open_questions": [],
                            "readiness": "ready_to_execute",
                        },
                        "handoff": {
                            "workflow_request": "Run ready workflow.",
                            "success_criteria": ["The workflow starts."],
                        },
                    },
                )

        with (
            tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as store,
            tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as repo,
            patch("coder_workbench.server.app.HarnessRuntimeManager", FakeHarnessRuntimeManager),
        ):
            client = TestClient(create_app(store_root=store, frontend_dist=store))
            session_id = _create_session(client, interaction_mode="work", repo=repo, agent_workflow=workflow)

            response = client.post(
                f"/api/v2/planner-chat/sessions/{session_id}/turn",
                json={"message": "Start working.", "interaction_mode": "work"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["run_id"])
        self.assertEqual(payload["status"], "running")

    def test_existing_draft_endpoint_still_works(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as store, tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as repo:
            client = TestClient(create_app(store_root=store, frontend_dist=store))
            response = client.post(
                "/api/v2/planner-chat/draft",
                json={
                    "request": "Update docs.",
                    "workflow_id": "default-planner-led",
                    "planner_agent_id": "planner",
                    "repo": repo,
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["artifact_type"], "project_plan_draft")


def _create_session(
    client: TestClient,
    *,
    interaction_mode: str = "discuss",
    repo: str | None = None,
    agent_workflow: dict | None = None,
) -> str:
    body = {
        "workflow_id": "default-planner-led",
        "planner_agent_id": "planner",
        "interaction_mode": interaction_mode,
    }
    if repo is not None:
        body["repo"] = repo
    if agent_workflow is not None:
        body["agent_workflow"] = agent_workflow
    response = client.post("/api/v2/planner-chat/sessions", json=body)
    assert response.status_code == 200, response.text
    return str(response.json()["session_id"])


if __name__ == "__main__":
    unittest.main()
