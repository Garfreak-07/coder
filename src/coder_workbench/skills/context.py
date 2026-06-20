from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from coder_workbench.skills.index import SkillIndexEntry
from coder_workbench.skills.router import SkillRouteDecision


class SkillContextRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill_id: str
    ref: str
    estimated_tokens: int
    load_mode: str = "on_demand"


class ContextPacketV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str
    work_item_id: str
    artifact_type: str
    included_skill_ids: list[str] = Field(default_factory=list)
    included_refs: list[str] = Field(default_factory=list)
    omitted_skill_ids: list[str] = Field(default_factory=list)
    omitted_refs: list[str] = Field(default_factory=list)
    estimated_input_tokens: int = 0
    estimated_omitted_tokens: int = 0
    compression_ratio: float = 0.0


def build_skill_context_refs(decision: SkillRouteDecision, skill_index: list[SkillIndexEntry]) -> list[SkillContextRef]:
    by_id = {skill.id: skill for skill in skill_index}
    refs: list[SkillContextRef] = []
    for skill_id in decision.allowed_skill_ids:
        skill = by_id.get(skill_id)
        if skill is None:
            continue
        refs.append(
            SkillContextRef(
                skill_id=skill.id,
                ref=f"skill:{skill.id}:SKILL.md",
                estimated_tokens=skill.max_skill_tokens,
            )
        )
    return refs
