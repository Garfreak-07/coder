from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .models import WorkflowSpec


def load_workflow_spec(path: str | Path) -> dict[str, Any]:
    spec_path = Path(path).expanduser().resolve()
    data = json.loads(spec_path.read_text(encoding="utf-8"))
    return validate_workflow_spec(data, source=str(spec_path))


def validate_workflow_spec(data: dict[str, Any], source: str = "<memory>") -> dict[str, Any]:
    try:
        spec = WorkflowSpec.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"Invalid workflow spec {source}: {exc}") from exc
    return spec.model_dump(mode="json")


def summarize_workflow_spec(spec: dict[str, Any]) -> str:
    lines = [
        f"{spec['name']} ({spec['id']})",
        spec.get("description", ""),
        f"max_loops: {spec['max_loops']}",
        "agents:",
        *[f"- {agent['id']}: {agent['role']}" for agent in spec.get("agents", [])],
        "steps:",
        *[f"- {step['id']} [{step['kind']}] uses {step['uses']}" for step in spec.get("steps", [])],
        "edges:",
        *[
            f"- {edge['source']} -> {edge['target']}"
            + (f" when {edge['condition']}" if edge.get("condition") else "")
            for edge in spec.get("edges", [])
        ],
        "stop_conditions:",
        *[f"- {condition}" for condition in spec.get("stop_conditions", [])],
    ]
    return "\n".join(line for line in lines if line is not None)

