from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .models import AgentCard
from .specs import validate_workflow_spec
from .tools.filesystem import resolve_existing_dir


CODER_DIR = ".coder"
WORKFLOWS_DIR = "workflows"
AGENTS_DIR = "agents"


def storage_root(repo: str | Path, *, create: bool = False) -> Path:
    root = resolve_existing_dir(str(repo))
    path = root / CODER_DIR
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def list_saved_workflows(repo: str | Path) -> list[dict[str, Any]]:
    return _list_json(storage_root(repo) / WORKFLOWS_DIR)


def list_saved_agents(repo: str | Path) -> list[dict[str, Any]]:
    return _list_json(storage_root(repo) / AGENTS_DIR)


def save_workflow(repo: str | Path, workflow: dict[str, Any]) -> dict[str, Any]:
    spec = validate_workflow_spec(workflow)
    target = storage_root(repo, create=True) / WORKFLOWS_DIR / f"{_safe_id(spec['id'])}.json"
    _write_json(target, spec)
    return spec


def save_agent(repo: str | Path, agent: dict[str, Any]) -> dict[str, Any]:
    card = AgentCard.model_validate(agent).model_dump(mode="json")
    target = storage_root(repo, create=True) / AGENTS_DIR / f"{_safe_id(card['id'])}.json"
    _write_json(target, card)
    return card


def _list_json(directory: Path) -> list[dict[str, Any]]:
    if not directory.exists():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            items.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return items


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _safe_id(value: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip()).strip(".-")
    return safe or "item"
