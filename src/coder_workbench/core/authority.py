from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from coder_workbench.core.agent_workflow import AgentWorkflowAgent


Authority = Literal["planner", "executor"]


class AgentAuthorityProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authority: Authority
    can_ask_human: bool = False
    can_write_long_term_memory: bool = False
    can_create_plan_graph: bool = False
    can_trigger_interrupt: bool = False
    can_modify_files: bool = False
    can_run_commands: bool = False
    allowed_artifact_types: list[str] = Field(default_factory=list)


PLANNER_PROFILE = AgentAuthorityProfile(
    authority="planner",
    can_ask_human=True,
    can_write_long_term_memory=True,
    can_create_plan_graph=True,
    allowed_artifact_types=["run_contract", "planner_order", "planner_decision", "round_summary"],
)

EXECUTOR_PROFILE = AgentAuthorityProfile(
    authority="executor",
    can_trigger_interrupt=True,
    can_modify_files=True,
    can_run_commands=True,
    allowed_artifact_types=["execution_result"],
)

AUTHORITY_PROFILES = {
    "planner": PLANNER_PROFILE,
    "executor": EXECUTOR_PROFILE,
}


def authority_profile_for_agent(agent: "AgentWorkflowAgent", *, primary_planner_id: str) -> AgentAuthorityProfile:
    if agent.id == primary_planner_id:
        return PLANNER_PROFILE
    return EXECUTOR_PROFILE


def authority_catalog() -> list[dict[str, object]]:
    return [
        profile.model_dump(mode="json")
        for profile in AUTHORITY_PROFILES.values()
    ]
