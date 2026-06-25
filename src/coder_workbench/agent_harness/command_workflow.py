from __future__ import annotations

from typing import Any

from coder_workbench.agent_harness.action_protocol import HarnessActionRequest


class CommandWorkflow:
    def result_failed(
        self,
        request: HarnessActionRequest,
        payload: dict[str, Any],
        status: str,
    ) -> bool:
        if request.action_type != "run_command_sandbox":
            return False
        command_result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        return bool(command_result and command_result.get("passed") is False and status == "ok")
