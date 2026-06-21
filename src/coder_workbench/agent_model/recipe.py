from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from coder_workbench.core import AgentWorkflowAgent


AgentRecipeRole = Literal[
    "planner",
    "do_work",
    "check_result",
    "organize",
    "research",
    "write_draft",
]


class AgentRecipe(BaseModel):
    """Ordinary user-facing Agent definition."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    role: AgentRecipeRole
    purpose: str = ""
    behavior_notes: list[str] = Field(default_factory=list)
    preferred_extension_ids: list[str] = Field(default_factory=list)


def recipe_from_workflow_agent(agent: "AgentWorkflowAgent", *, primary_planner_id: str) -> AgentRecipe:
    return AgentRecipe(
        id=agent.id,
        name=agent.name,
        role=_recipe_role(agent, primary_planner_id=primary_planner_id),
        purpose=agent.purpose,
    )


def _recipe_role(agent: "AgentWorkflowAgent", *, primary_planner_id: str) -> AgentRecipeRole:
    if agent.id == primary_planner_id or agent.role == "planner":
        return "planner"
    if agent.role_card == "check_result" or agent.role in {"tester", "reviewer"}:
        return "check_result"
    if agent.role_card == "organize_information" or agent.role == "summarizer":
        return "organize"
    if agent.role_card == "research_sources" or agent.role == "researcher":
        return "research"
    if agent.role_card == "write_draft" or agent.role == "writer":
        return "write_draft"
    return "do_work"
