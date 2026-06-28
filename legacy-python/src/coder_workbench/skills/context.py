from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from coder_workbench.skills.index import SkillIndexEntry
from coder_workbench.skills.ledger import estimate_tokens
from coder_workbench.skills.router import SkillRouteDecision
from coder_workbench.skills.store import InstalledSkillStore


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


class SkillLoadedContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill_id: str
    ref: str
    content: str
    estimated_tokens: int
    truncated: bool = False
    load_mode: str = "on_demand"


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


def load_selected_skill_contexts(
    *,
    skill_store_root: str | Path,
    decision: SkillRouteDecision,
    skill_index: list[SkillIndexEntry],
    task_summary: str,
) -> list[SkillLoadedContext]:
    store = InstalledSkillStore(skill_store_root)
    by_id = {skill.id: skill for skill in skill_index}
    contexts: list[SkillLoadedContext] = []
    for skill_id in decision.allowed_skill_ids:
        skill = by_id.get(skill_id)
        if skill is None:
            continue
        try:
            body = store.read_skill_body(skill_id)
        except (KeyError, OSError, UnicodeDecodeError):
            continue
        selected, truncated = _select_relevant_text(
            body,
            query=task_summary,
            max_tokens=skill.max_skill_tokens,
        )
        contexts.append(
            SkillLoadedContext(
                skill_id=skill.id,
                ref=f"skill:{skill.id}:SKILL.md",
                content=selected,
                estimated_tokens=estimate_tokens(selected),
                truncated=truncated,
            )
        )
    return contexts


def _select_relevant_text(text: str, *, query: str, max_tokens: int) -> tuple[str, bool]:
    max_chars = max(0, max_tokens) * 4
    if max_chars <= 0:
        return "", bool(text)
    if len(text) <= max_chars:
        return text, False

    sections = _markdown_sections(text)
    query_tokens = _tokens(query)
    ranked = sorted(
        enumerate(sections),
        key=lambda item: (-_section_score(item[1], query_tokens), item[0]),
    )
    selected: list[str] = []
    used = 0
    for _index, section in ranked:
        section = section.strip()
        if not section:
            continue
        remaining = max_chars - used
        if remaining <= 0:
            break
        chunk = section[:remaining]
        selected.append(chunk)
        used += len(chunk)
        if used >= max_chars:
            break
    if not selected:
        return text[:max_chars], True
    return "\n\n".join(selected), True


def _markdown_sections(text: str) -> list[str]:
    sections: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if line.startswith("#") and current:
            sections.append("\n".join(current))
            current = [line]
            continue
        current.append(line)
    if current:
        sections.append("\n".join(current))
    return sections


def _section_score(section: str, query_tokens: set[str]) -> int:
    if not query_tokens:
        return 0
    return len(_tokens(section).intersection(query_tokens))


def _tokens(text: str) -> set[str]:
    return {token for token in re.split(r"[^a-zA-Z0-9_]+", text.lower()) if token}
