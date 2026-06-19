from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any, Literal

from coder_graph_v2.core import AgentSpec, WorkflowSpec


LibraryKind = Literal["agents", "workflows"]


class LibraryStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self._lock = Lock()
        (self.root / "agents").mkdir(parents=True, exist_ok=True)
        (self.root / "workflows").mkdir(parents=True, exist_ok=True)

    def list_agents(self) -> list[dict[str, Any]]:
        return self._list("agents")

    def list_workflows(self) -> list[dict[str, Any]]:
        return self._list("workflows")

    def save_agent(self, data: dict[str, Any]) -> dict[str, Any]:
        agent = AgentSpec.model_validate(data)
        payload = agent.model_dump(mode="json")
        self._write("agents", agent.id, payload)
        return payload

    def save_workflow(self, data: dict[str, Any]) -> dict[str, Any]:
        workflow = WorkflowSpec.model_validate(data)
        payload = workflow.model_dump(mode="json", by_alias=True)
        self._write("workflows", workflow.id, payload)
        return payload

    def get_agent(self, agent_id: str) -> dict[str, Any]:
        return self._read("agents", agent_id)

    def get_workflow(self, workflow_id: str) -> dict[str, Any]:
        return self._read("workflows", workflow_id)

    def _list(self, kind: LibraryKind) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for path in sorted((self.root / kind).glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            items.append(_summary(kind, data))
        return items

    def _write(self, kind: LibraryKind, item_id: str, payload: dict[str, Any]) -> None:
        with self._lock:
            self._path(kind, item_id).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _read(self, kind: LibraryKind, item_id: str) -> dict[str, Any]:
        path = self._path(kind, item_id)
        if not path.exists():
            raise KeyError(item_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def _path(self, kind: LibraryKind, item_id: str) -> Path:
        safe = "".join(char for char in item_id if char.isalnum() or char in {"-", "_"})
        return self.root / kind / f"{safe}.json"


def _summary(kind: LibraryKind, data: dict[str, Any]) -> dict[str, Any]:
    if kind == "agents":
        return {
            "id": data.get("id"),
            "name": data.get("name"),
            "role": data.get("role"),
            "goal": data.get("goal"),
            "model": data.get("model"),
            "tools": data.get("tools", []),
        }
    return {
        "id": data.get("id"),
        "version": data.get("version"),
        "name": data.get("name"),
        "description": data.get("description", ""),
        "nodes": len(data.get("nodes", [])),
        "edges": len(data.get("edges", [])),
        "agents": len(data.get("agents", [])),
    }
