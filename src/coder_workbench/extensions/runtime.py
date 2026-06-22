from __future__ import annotations

from typing import Any

from coder_workbench.tools import default_tool_registry


class ExtensionRuntime:
    """Executes plugin operations through the locked runtime boundary."""

    def __init__(self, *, registry: Any | None = None) -> None:
        self.registry = registry or default_tool_registry()

    def capability(self, operation_id: str) -> Any | None:
        if hasattr(self.registry, "capability"):
            return self.registry.capability(operation_id)
        return None

    def execute_plugin_operation(
        self,
        operation_id: str,
        args: dict[str, Any],
        runtime_context: dict[str, Any],
    ) -> dict[str, Any]:
        result = self.registry.run(operation_id, args, runtime_context)
        return {
            "operation_id": operation_id,
            "status": result.get("status") or ("completed" if not result.get("blocked") else "blocked"),
            "requires_preview": bool(result.get("requires_approval") or result.get("requires_preview")),
            "result": result,
        }
