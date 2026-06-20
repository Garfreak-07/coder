from __future__ import annotations

import json
from typing import Any, Callable
from uuid import uuid4

from coder_workbench.core.artifacts import (
    ArtifactValidationError,
    artifact_summary,
    supported_artifact_types,
    validate_artifact,
)
from coder_workbench.runtime.state import RunState


BlockRun = Callable[[RunState, str], None]


def record_agent_artifact(
    state: RunState,
    node_id: str,
    result: dict[str, Any],
    *,
    expected_type: str | None,
    block_run: BlockRun,
) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None
    candidate_type = expected_type or str(result.get("artifact_type") or "")
    if not candidate_type:
        return None
    if candidate_type not in supported_artifact_types():
        state.emit(
            "artifact.validation_failed",
            f"Unsupported artifact type: {candidate_type}",
            node_id=node_id,
            artifact_type=candidate_type,
            errors=[{"loc": ["artifact_type"], "msg": f"unsupported artifact type: {candidate_type}"}],
        )
        block_run(state, "artifact validation failed")
        return result

    artifact_id = f"artifact_{uuid4().hex}"
    try:
        artifact = validate_artifact(result, expected_type=expected_type, artifact_id=artifact_id)
    except ArtifactValidationError as exc:
        state.emit(
            "artifact.validation_failed",
            f"{exc.artifact_type} failed schema validation",
            node_id=node_id,
            artifact_type=exc.artifact_type,
            errors=exc.errors,
        )
        block_run(state, "artifact validation failed")
        return result

    summary = artifact_summary(artifact)
    state.artifacts[artifact_id] = artifact
    state.emit(
        "artifact.produced",
        f"Artifact {artifact_id} produced",
        node_id=node_id,
        artifact_id=artifact_id,
        artifact_type=artifact["artifact_type"],
        summary=summary,
        size_chars=len(json.dumps(artifact, ensure_ascii=False)),
    )
    return artifact
