from __future__ import annotations

import os
import unittest
from typing import Any

from coder_workbench.harness_runtime import HarnessRuntimeContext, HarnessRuntimeManager, OpenHandsRuntimeProvider
from coder_workbench.harness_runtime.profiles import OPENHANDS_PROVIDER_ID
from coder_workbench.harness_runtime.runtime_context import HarnessRunRequest, HarnessRunResult


class OpenHandsRuntimeProviderTests(unittest.TestCase):
    def test_openhands_provider_fails_closed_when_sdk_missing(self) -> None:
        provider = OpenHandsRuntimeProvider(runtime_module_names=("definitely_missing_openhands_sdk",))
        request = _request()

        self.assertFalse(provider.is_available())
        result = provider.run(request)

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error["code"], "openhands_sdk_unavailable")
        self.assertEqual(len(result.native_event_refs), 1)

    def test_manager_falls_back_when_openhands_flag_disabled(self) -> None:
        provider = _FakeOpenHandsProvider()
        manager = HarnessRuntimeManager(providers=[provider, _FakeFallbackProvider()])

        with _env("CODER_ENABLE_OPENHANDS_RUNTIME", None):
            result = manager.run_workflow_supervisor(context=_context())

        self.assertEqual(result.error["code"], "fallback_used")
        self.assertEqual(provider.calls, 0)

    def test_manager_uses_openhands_provider_when_flag_enabled_and_available(self) -> None:
        provider = _FakeOpenHandsProvider()
        manager = HarnessRuntimeManager(providers=[provider, _FakeFallbackProvider()])

        with _env("CODER_ENABLE_OPENHANDS_RUNTIME", "1"):
            result = manager.run_workflow_supervisor(context=_context())

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.artifact_type, "final_report")
        self.assertEqual(provider.calls, 1)


class _FakeOpenHandsProvider:
    provider_id = OPENHANDS_PROVIDER_ID

    def __init__(self) -> None:
        self.calls = 0

    def is_available(self) -> bool:
        return True

    def run(self, request: HarnessRunRequest, *, emit: Any | None = None) -> HarnessRunResult:
        self.calls += 1
        return HarnessRunResult(
            status="completed",
            artifact_type="final_report",
            artifact={"artifact_type": "final_report", "status": "completed", "summary": "ok"},
        )


class _FakeFallbackProvider:
    provider_id = "internal-fallback"

    def is_available(self) -> bool:
        return True

    def run(self, request: HarnessRunRequest, *, emit: Any | None = None) -> HarnessRunResult:
        return HarnessRunResult(status="failed", error={"code": "fallback_used", "message": "fallback"})


class _env:
    def __init__(self, key: str, value: str | None) -> None:
        self.key = key
        self.value = value
        self.old = os.environ.get(key)

    def __enter__(self) -> None:
        if self.value is None:
            os.environ.pop(self.key, None)
        else:
            os.environ[self.key] = self.value

    def __exit__(self, *_args: object) -> None:
        if self.old is None:
            os.environ.pop(self.key, None)
        else:
            os.environ[self.key] = self.old


def _context() -> HarnessRuntimeContext:
    return HarnessRuntimeContext(
        run_id="run-1",
        agent_id="planner",
        workflow_id="workflow-1",
        harness_id="conversation-harness",
        mode="workflow_supervisor",
        profile_id="openhands-workflow-supervisor-default",
    )


def _request() -> HarnessRunRequest:
    manager = HarnessRuntimeManager()
    return manager._request(
        request_id="request-1",
        contract_id="conversation-harness",
        mode="workflow_supervisor",
        profile_id="openhands-workflow-supervisor-default",
        context=_context(),
        input_artifacts={},
    )


if __name__ == "__main__":
    unittest.main()
