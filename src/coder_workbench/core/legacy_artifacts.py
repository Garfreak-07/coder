from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from coder_workbench.core.planner_artifacts import RiskLevel


LegacyArtifactType = Literal["plan_artifact", "patch_artifact", "review_artifact"]
ReviewStatus = Literal["pass", "needs_changes", "failed", "blocked"]


class LegacyArtifactBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str | None = None
    artifact_type: LegacyArtifactType


class PlanArtifact(LegacyArtifactBase):
    artifact_type: Literal["plan_artifact"] = "plan_artifact"
    summary: str
    target_files: list[str] = Field(default_factory=list)
    required_context: list[str] = Field(default_factory=list)
    implementation_steps: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    recommended_checks: list[str] = Field(default_factory=list)
    executor_instructions: str = ""


class PatchArtifact(LegacyArtifactBase):
    artifact_type: Literal["patch_artifact"] = "patch_artifact"
    implementation_summary: str
    changed_files: list[str] = Field(default_factory=list)
    patches: list[dict[str, Any]] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    suggested_check_command: str = ""


class ReviewArtifact(LegacyArtifactBase):
    artifact_type: Literal["review_artifact"] = "review_artifact"
    status: ReviewStatus
    evidence: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = "low"
    recommended_action: str = ""


LEGACY_ARTIFACT_MODELS: dict[str, type[LegacyArtifactBase]] = {
    "plan_artifact": PlanArtifact,
    "patch_artifact": PatchArtifact,
    "review_artifact": ReviewArtifact,
}


def legacy_artifact_summary(artifact: dict[str, Any]) -> dict[str, Any]:
    artifact_type = str(artifact.get("artifact_type") or "")
    if artifact_type == "plan_artifact":
        return {
            "summary": artifact.get("summary"),
            "target_files": artifact.get("target_files", []),
            "steps": len(artifact.get("implementation_steps", [])),
            "risks": len(artifact.get("risks", [])),
            "checks": artifact.get("recommended_checks", []),
        }
    if artifact_type == "patch_artifact":
        return {
            "summary": artifact.get("implementation_summary"),
            "changed_files": artifact.get("changed_files", []),
            "patches": len(artifact.get("patches", [])),
            "risks": len(artifact.get("risks", [])),
            "suggested_check_command": artifact.get("suggested_check_command"),
        }
    if artifact_type == "review_artifact":
        return {
            "status": artifact.get("status"),
            "risk_level": artifact.get("risk_level"),
            "issues": len(artifact.get("issues", [])),
            "recommended_action": artifact.get("recommended_action"),
        }
    return {}
