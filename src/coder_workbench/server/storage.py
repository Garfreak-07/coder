from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from coder_workbench.runtime import RunEvent, RunResult


class StoredRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: str(uuid4()))
    workflow_id: str
    repo_root: str
    request: str
    result: RunResult


class StoredRunMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    workflow_id: str
    repo_root: str
    request: str
    status: str
    events: int
    agent_calls: int
    tool_calls: int
    estimated_tokens_used: int


class RunStore:
    """Small file-backed store for workflow runs.

    This is intentionally simple. It gives the upcoming app a stable run/event
    API without committing to a database before the frontend shape is settled.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.runs_dir = self.root / "runs"
        self.live_runs_dir = self.root / "live-runs"
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.live_runs_dir.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def save(self, workflow_id: str, repo_root: str, request: str, result: RunResult) -> StoredRun:
        stored = StoredRun(workflow_id=workflow_id, repo_root=repo_root, request=request, result=result)
        with self._lock:
            run_dir = self._run_dir(stored.id)
            run_dir.mkdir(parents=True, exist_ok=True)
            metadata = StoredRunMetadata(
                id=stored.id,
                workflow_id=workflow_id,
                repo_root=repo_root,
                request=request,
                status=result.status,
                events=len(result.events),
                agent_calls=result.agent_calls,
                tool_calls=result.tool_calls,
                estimated_tokens_used=result.estimated_tokens_used,
            )
            (run_dir / "metadata.json").write_text(metadata.model_dump_json(indent=2), encoding="utf-8")
            result_payload = result.model_dump(mode="json")
            result_payload["events"] = []
            (run_dir / "result.json").write_text(json.dumps(result_payload, indent=2), encoding="utf-8")
            self._write_events(run_dir / "events.jsonl", result.events)
        return stored

    def get(self, run_id: str, *, include_events: bool = True) -> StoredRun:
        run_dir = self._run_dir(run_id)
        if run_dir.exists():
            return self._read_split_run(run_dir, include_events=include_events)

        path = self._legacy_path(run_id)
        if not path.exists():
            raise KeyError(run_id)
        stored = StoredRun.model_validate(json.loads(path.read_text(encoding="utf-8")))
        if include_events:
            return stored
        result_payload = stored.result.model_dump(mode="json")
        result_payload["events"] = []
        return StoredRun(
            id=stored.id,
            workflow_id=stored.workflow_id,
            repo_root=stored.repo_root,
            request=stored.request,
            result=RunResult.model_validate(result_payload),
        )

    def list(self) -> list[dict[str, Any]]:
        runs: list[dict[str, Any]] = []
        items = list(self.runs_dir.glob("*/metadata.json")) + list(self.runs_dir.glob("*.json"))
        for path in sorted(items, key=lambda item: item.stat().st_mtime, reverse=True):
            try:
                if path.name == "metadata.json":
                    metadata = StoredRunMetadata.model_validate(json.loads(path.read_text(encoding="utf-8")))
                    runs.append(metadata.model_dump(mode="json"))
                    continue
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

    def get_events(self, run_id: str, *, cursor: int = 0, limit: int | None = None) -> dict[str, Any]:
        if cursor < 0:
            raise ValueError("cursor must be greater than or equal to zero")
        if limit is not None and limit < 1:
            raise ValueError("limit must be greater than zero")

        run_dir = self._run_dir(run_id)
        if run_dir.exists():
            all_events = self._read_events(run_dir / "events.jsonl")
        else:
            stored = self.get(run_id)
            all_events = stored.result.events

        end = None if limit is None else cursor + limit
        events = all_events[cursor:end]
        next_cursor = cursor + len(events)
        return {
            "events": [event.model_dump(mode="json") for event in events],
            "cursor": cursor,
            "next_cursor": next_cursor,
            "has_more": next_cursor < len(all_events),
        }

    def _safe_run_id(self, run_id: str) -> str:
        safe = "".join(char for char in run_id if char.isalnum() or char in {"-", "_"})
        if not safe:
            raise KeyError(run_id)
        return safe

    def _run_dir(self, run_id: str) -> Path:
        return self.runs_dir / self._safe_run_id(run_id)

    def _legacy_path(self, run_id: str) -> Path:
        return self.runs_dir / f"{self._safe_run_id(run_id)}.json"

    def _read_split_run(self, run_dir: Path, *, include_events: bool) -> StoredRun:
        metadata = StoredRunMetadata.model_validate(json.loads((run_dir / "metadata.json").read_text(encoding="utf-8")))
        result_payload = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
        result_payload["events"] = [
            event.model_dump(mode="json")
            for event in self._read_events(run_dir / "events.jsonl")
        ] if include_events else []
        return StoredRun(
            id=metadata.id,
            workflow_id=metadata.workflow_id,
            repo_root=metadata.repo_root,
            request=metadata.request,
            result=RunResult.model_validate(result_payload),
        )

    def _write_events(self, path: Path, events: list[RunEvent]) -> None:
        lines = [json.dumps(event.model_dump(mode="json"), ensure_ascii=False) for event in events]
        path.write_text(("\n".join(lines) + "\n") if lines else "", encoding="utf-8")

    def _read_events(self, path: Path) -> list[RunEvent]:
        if not path.exists():
            return []
        events = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            events.append(RunEvent.model_validate(json.loads(line)))
        return events

    def save_live(self, payload: dict[str, Any]) -> None:
        run_id = str(payload.get("id") or "")
        if not run_id:
            raise ValueError("live run payload requires id")
        with self._lock:
            self._live_path(run_id).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def list_live(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for path in sorted(self.live_runs_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(payload, dict):
                items.append(payload)
        return items

    def _live_path(self, run_id: str) -> Path:
        safe = "".join(char for char in run_id if char.isalnum() or char in {"-", "_"})
        return self.live_runs_dir / f"{safe}.json"
