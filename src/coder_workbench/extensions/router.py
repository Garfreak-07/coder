from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from coder_workbench.skills import SkillIndex, SkillRouteDecision, SkillRouter


class ExtensionRouteDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    work_item_id: str
    plugin_ids: list[str] = Field(default_factory=list)
    skill_route: SkillRouteDecision
    estimated_token_impact: int = 0


class ExtensionRouter:
    def __init__(self, skill_index: SkillIndex, *, max_skills: int = 5, max_skill_tokens: int = 4000) -> None:
        self.skill_index = skill_index
        self.skill_router = SkillRouter(skill_index, max_skills=max_skills, max_skill_tokens=max_skill_tokens)

    def route_skills(
        self,
        *,
        user_request: str,
        work_item: Any,
        role: str,
        risk_policy: str = "normal",
    ) -> SkillRouteDecision:
        if not self.skill_index.skills:
            work_item_id = str(getattr(work_item, "work_item_id", "") or "")
            return SkillRouteDecision(work_item_id=work_item_id)
        return self.skill_router.select(
            user_request=user_request,
            work_item=work_item,
            role=role,
            risk_policy=risk_policy,
        )
