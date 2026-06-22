from __future__ import annotations

import tempfile
import time
import unittest

from fastapi.testclient import TestClient

from coder_workbench.core import default_planner_led_agent_workflow
from coder_workbench.server.app import create_app


class RunHeartbeatTests(unittest.TestCase):
    def test_live_run_heartbeat_endpoint_returns_liveness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = TestClient(create_app(store_root=tmp, frontend_dist=tmp))
            response = client.post(
                "/api/v2/live-agent-runs",
                json={
                    "repo": tmp,
                    "request": "Run default workflow.",
                    "agent_workflow": default_planner_led_agent_workflow().model_dump(mode="json", by_alias=True),
                    "approved": True,
                },
            )
            run_id = response.json()["run_id"]
            heartbeat = client.get(f"/api/v2/live-agent-runs/{run_id}/heartbeat")

        self.assertEqual(heartbeat.status_code, 200)
        payload = heartbeat.json()
        self.assertEqual(payload["run_id"], run_id)
        self.assertIn(payload["status"], {"queued", "running", "completed", "blocked", "failed", "cancelled"})
        self.assertTrue(payload["last_heartbeat_at"])
        self.assertIn("active_work_item_ids", payload)

    def test_live_run_control_endpoints_reject_completed_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = TestClient(create_app(store_root=tmp, frontend_dist=tmp))
            response = client.post(
                "/api/v2/live-agent-runs",
                json={
                    "repo": tmp,
                    "request": "Run default workflow.",
                    "agent_workflow": default_planner_led_agent_workflow().model_dump(mode="json", by_alias=True),
                    "approved": True,
                },
            )
            run_id = response.json()["run_id"]
            for _ in range(100):
                detail = client.get(f"/api/v2/live-agent-runs/{run_id}").json()
                if detail["status"] not in {"queued", "running"}:
                    break
                time.sleep(0.02)
            pause = client.post(f"/api/v2/live-agent-runs/{run_id}/pause")

        self.assertEqual(pause.status_code, 409)


if __name__ == "__main__":
    unittest.main()
