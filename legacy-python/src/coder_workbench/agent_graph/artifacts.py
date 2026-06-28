from __future__ import annotations

import json
from typing import Any, Callable

from coder_workbench.core.artifacts import artifact_summary, supported_artifact_types, validate_artifact


EmitEvent = Callable[..., None]


class AgentGraphArtifactRecorder:
    def __init__(self, artifacts: dict[str, Any], emit: EmitEvent) -> None:
        self.artifacts = artifacts
        self.emit = emit

    def record(
        self,
        artifact_id: str,
        payload: dict[str, Any],
        *,
        expected_type: str | None = None,
    ) -> dict[str, Any]:
        artifact_type = expected_type or str(payload.get("artifact_type") or "")
        if artifact_type in supported_artifact_types():
            artifact = validate_artifact(payload, expected_type=artifact_type, artifact_id=artifact_id)
        else:
            artifact = dict(payload)
            artifact["artifact_id"] = artifact_id
        self.artifacts[artifact_id] = artifact
        self.emit(
            "artifact.produced",
            f"Artifact {artifact_id} produced",
            artifact_id=artifact_id,
            artifact_type=artifact.get("artifact_type"),
            summary=artifact_summary(artifact),
            size_chars=len(json.dumps(artifact, ensure_ascii=False)),
        )
        return artifact


def graph_artifact_id(*parts: Any) -> str:
    segments = [_safe_artifact_part(part) for part in parts if str(part).strip()]
    return "_".join(segments) or "artifact"


def _safe_artifact_part(value: Any) -> str:
    safe = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in str(value).strip())
    return safe.strip("_") or "artifact"
