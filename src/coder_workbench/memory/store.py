from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from coder_workbench.agent_graph.memory import PlannerMemoryStore, WorkflowMemory
from coder_workbench.memory.schema import WorkflowMemoryCollection


class WorkflowMemoryStore:
    """Workflow memory adapter over the existing PlannerMemoryStore layout."""

    def __init__(self, repo_root: str | Path) -> None:
        self._legacy = PlannerMemoryStore(repo_root)

    def load_workflow_memory(self, workflow_id: str) -> WorkflowMemory:
        return self._legacy.load_workflow_memory(workflow_id)

    def save_workflow_memory(self, memory: WorkflowMemory) -> None:
        self._legacy.save_workflow_memory(memory)

    def append_entry(
        self,
        *,
        workflow_id: str,
        collection: WorkflowMemoryCollection,
        entry: dict[str, Any],
    ) -> WorkflowMemory:
        memory = self.load_workflow_memory(workflow_id)
        getattr(memory, collection).append(dict(entry))
        memory.updated_at = _now()
        self.save_workflow_memory(memory)
        return memory


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
