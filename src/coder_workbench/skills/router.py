from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from coder_workbench.skills.index import SkillIndex, SkillIndexEntry


class SkillRouteDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    work_item_id: str
    allowed_skill_ids: list[str] = Field(default_factory=list)
    loaded_skill_refs: list[str] = Field(default_factory=list)
    omitted_skill_ids: list[str] = Field(default_factory=list)
    estimated_skill_tokens: int = 0
    scores: dict[str, float] = Field(default_factory=dict)


class SkillRouter:
    def __init__(self, skill_index: SkillIndex, *, max_skills: int = 5, max_skill_tokens: int = 4000) -> None:
        self.skill_index = skill_index
        self.max_skills = max(1, max_skills)
        self.max_skill_tokens = max(0, max_skill_tokens)

    def select(
        self,
        *,
        user_request: str,
        work_item: Any,
        role: str,
        risk_policy: str = "normal",
    ) -> SkillRouteDecision:
        work_item_id = str(getattr(work_item, "work_item_id", None) or _dict_get(work_item, "work_item_id") or "")
        task_summary = str(getattr(work_item, "task_summary", None) or _dict_get(work_item, "task_summary") or "")
        produces = _string_list(getattr(work_item, "produces", None) or _dict_get(work_item, "produces"))
        requires = _string_list(getattr(work_item, "requires", None) or _dict_get(work_item, "requires"))
        scored = [
            (skill, _score_skill(skill, user_request=user_request, task_summary=task_summary, role=role, produces=produces, requires=requires, risk_policy=risk_policy))
            for skill in self.skill_index.enabled()
        ]
        scored = [(skill, score) for skill, score in scored if score > 0]
        scored.sort(key=lambda item: (-item[1], item[0].id))

        selected: list[SkillIndexEntry] = []
        token_total = 0
        for skill, _score in scored:
            next_tokens = token_total + skill.max_skill_tokens
            if selected and next_tokens > self.max_skill_tokens:
                continue
            selected.append(skill)
            token_total += skill.max_skill_tokens
            if len(selected) >= self.max_skills:
                break
        selected_ids = [skill.id for skill in selected]
        return SkillRouteDecision(
            work_item_id=work_item_id,
            allowed_skill_ids=selected_ids,
            loaded_skill_refs=[f"skill:{skill.id}:SKILL.md" for skill in selected],
            omitted_skill_ids=[skill.id for skill, _score in scored if skill.id not in selected_ids],
            estimated_skill_tokens=token_total,
            scores={skill.id: round(score, 4) for skill, score in scored},
        )


def select_skills_for_work_item(
    *,
    skill_index: SkillIndex,
    user_request: str,
    work_item: Any,
    role: str,
    risk_policy: str = "normal",
) -> SkillRouteDecision:
    return SkillRouter(skill_index).select(
        user_request=user_request,
        work_item=work_item,
        role=role,
        risk_policy=risk_policy,
    )


def _score_skill(
    skill: SkillIndexEntry,
    *,
    user_request: str,
    task_summary: str,
    role: str,
    produces: list[str],
    requires: list[str],
    risk_policy: str,
) -> float:
    text_tokens = _tokens(f"{user_request} {task_summary}")
    skill_tokens = _tokens(f"{skill.name} {skill.description} {' '.join(skill.when_to_use)} {skill.category}")
    keyword_match = _overlap_ratio(text_tokens, skill_tokens)
    produces_requires_match = _overlap_ratio(set(produces + requires), set(skill.produces + skill.requires))
    category_match = 1.0 if skill.category.lower() in text_tokens else 0.0
    role_fit = _role_fit(skill, role)
    trust = {"official": 1.0, "verified": 0.85, "community": 0.55, "local": 0.35, "untrusted": 0.0}[skill.trust_level]
    token_cost = min(1.0, skill.max_skill_tokens / 4000)
    risk_penalty = {"low": 0.0, "medium": 0.5, "high": 1.0}[skill.risk_level]
    if risk_policy == "strict":
        risk_penalty *= 1.5
    return (
        0.35 * keyword_match
        + 0.25 * produces_requires_match
        + 0.15 * category_match
        + 0.10 * role_fit
        + 0.10 * trust
        - 0.15 * token_cost
        - 0.20 * risk_penalty
    )


def _role_fit(skill: SkillIndexEntry, role: str) -> float:
    role_text = role.lower()
    if role_text in skill.when_to_use or role_text == skill.category.lower():
        return 1.0
    if role_text == "executor" and skill.category.lower() in {"coding", "execution", "research"}:
        return 1.0
    if role_text == "tester" and skill.category.lower() in {"evaluation", "testing"}:
        return 1.0
    return 0.3


def _tokens(text: str) -> set[str]:
    return {token for token in re.split(r"[^a-zA-Z0-9_]+", text.lower()) if token}


def _overlap_ratio(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left.intersection(right)) / max(1, len(left))


def _dict_get(value: Any, key: str) -> Any:
    return value.get(key) if isinstance(value, dict) else None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]
