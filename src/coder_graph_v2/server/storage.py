from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from coder_graph_v2.runtime import RunResult


class StoredRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: str(uuid4()))
    workflow_id: str
    repo_root: str
    request: str
    result: RunResult


class RunStore:
    """Small file-backed store for v2 runs.

    This is intentionally simple. It gives the upcoming app a stable run/event
    API without committing to a database before the frontend shape is settled.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.runs_dir = self.root / "runs"
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def save(self, workflow_id: str, repo_root: str, request: str, result: RunResult) -> StoredRun:
        stored = StoredRun(workflow_id=workflow_id, repo_root=repo_root, request=request, result=result)
        with self._lock:
            path = self._path(stored.id)
            path.write_text(stored.model_dump_json(indent=2), encoding="utf-8")
        return stored

    def get(self, run_id: str) -> StoredRun:
        path = self._path(run_id)
        if not path.exists():
            raise KeyError(run_id)
        return StoredRun.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def list(self) -> list[dict[str, Any]]:
        runs: list[dict[str, Any]] = []
        for path in sorted(self.runs_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
            try:
                stored = StoredRun.model_validate(json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                continue
            runs.append(
                {
                    "id": stored.id,
                    "workflow_id": stored.workflow_id,
                    "repo_root": stored.repo_root,
                    "request": stored.request,
                    "status": stored.result.status,
                    "events": len(stored.result.events),
                    "agent_calls": stored.result.agent_calls,
                    "tool_calls": stored.result.tool_calls,
                    "estimated_tokens_used": stored.result.estimated_tokens_used,
                }
            )
        return runs

    def _path(self, run_id: str) -> Path:
        safe = "".join(char for char in run_id if char.isalnum() or char in {"-", "_"})
        return self.runs_dir / f"{safe}.json"
