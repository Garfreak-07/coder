from __future__ import annotations

import threading
import time
import unittest
from typing import Any

from coder_workbench.actions import ToolExecutionResult, ToolExecutionService, ToolExecutionSpec


class ToolExecutionServiceTests(unittest.TestCase):
    def test_read_only_batch_runs_concurrently(self) -> None:
        service = ToolExecutionService()
        specs = [
            ToolExecutionSpec(action_id=f"read-{index}", action_type="read", input={}, is_read_only=True)
            for index in range(3)
        ]

        started = time.monotonic()
        results = service.run_batch(specs, object(), handler=_sleeping_handler(0.15))
        elapsed = time.monotonic() - started

        self.assertEqual([result.action_id for result in results], ["read-0", "read-1", "read-2"])
        self.assertTrue(all(result.status == "ok" for result in results))
        self.assertLess(elapsed, 0.35)

    def test_exclusive_action_runs_alone_between_parallel_groups(self) -> None:
        service = ToolExecutionService()
        specs = [
            ToolExecutionSpec(action_id="read-1", action_type="read", input={}, is_read_only=True),
            ToolExecutionSpec(action_id="exclusive", action_type="write", input={}, requires_exclusive_access=True),
            ToolExecutionSpec(action_id="read-2", action_type="read", input={}, is_read_only=True),
        ]
        active = 0
        max_active_by_action: dict[str, int] = {}
        lock = threading.Lock()

        def handler(spec: ToolExecutionSpec, _: Any) -> ToolExecutionResult:
            nonlocal active
            with lock:
                active += 1
                max_active_by_action[spec.action_id] = active
            time.sleep(0.05)
            with lock:
                active -= 1
            return ToolExecutionResult(
                action_id=spec.action_id,
                action_type=spec.action_type,
                status="ok",
                summary="ok",
                payload={},
            )

        results = service.run_batch(specs, object(), handler=handler)

        self.assertEqual([result.action_id for result in results], ["read-1", "exclusive", "read-2"])
        self.assertEqual(max_active_by_action["exclusive"], 1)

    def test_result_order_is_preserved(self) -> None:
        service = ToolExecutionService()
        specs = [
            ToolExecutionSpec(action_id="slow", action_type="read", input={"sleep": 0.15}, is_read_only=True),
            ToolExecutionSpec(action_id="fast", action_type="read", input={"sleep": 0.01}, is_read_only=True),
        ]

        def handler(spec: ToolExecutionSpec, _: Any) -> ToolExecutionResult:
            time.sleep(float(spec.input["sleep"]))
            return ToolExecutionResult(
                action_id=spec.action_id,
                action_type=spec.action_type,
                status="ok",
                summary=spec.action_id,
                payload={},
            )

        results = service.run_batch(specs, object(), handler=handler)

        self.assertEqual([result.action_id for result in results], ["slow", "fast"])

    def test_timeout_returns_structured_result(self) -> None:
        service = ToolExecutionService()
        spec = ToolExecutionSpec(
            action_id="timeout",
            action_type="read",
            input={},
            is_read_only=True,
            timeout_seconds=0.01,  # type: ignore[arg-type]
        )

        result = service.run_one(spec, object(), handler=_sleeping_handler(0.2))

        self.assertEqual(result.status, "timeout")
        self.assertEqual(result.error_code, "action_timeout")
        self.assertIn("timed out", result.summary)

    def test_failure_can_cancel_pending_work(self) -> None:
        service = ToolExecutionService()
        specs = [
            ToolExecutionSpec(
                action_id="fail",
                action_type="write",
                input={},
                requires_exclusive_access=True,
                cancel_pending_on_failure=True,
            ),
            ToolExecutionSpec(action_id="pending", action_type="read", input={}, is_read_only=True),
        ]

        def handler(spec: ToolExecutionSpec, _: Any) -> ToolExecutionResult:
            return ToolExecutionResult(
                action_id=spec.action_id,
                action_type=spec.action_type,
                status="failed",
                summary="failed",
                payload={},
                error_code="boom",
            )

        results = service.run_batch(specs, object(), handler=handler)

        self.assertEqual(results[0].status, "failed")
        self.assertEqual(results[1].status, "cancelled")
        self.assertEqual(results[1].error_code, "cancelled_by_prior_failure")


def _sleeping_handler(seconds: float):
    def handler(spec: ToolExecutionSpec, _: Any) -> ToolExecutionResult:
        time.sleep(seconds)
        return ToolExecutionResult(
            action_id=spec.action_id,
            action_type=spec.action_type,
            status="ok",
            summary="ok",
            payload={},
        )

    return handler


if __name__ == "__main__":
    unittest.main()
