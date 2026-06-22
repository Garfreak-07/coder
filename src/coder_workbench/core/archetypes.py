from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

from coder_workbench.core.authority import AgentAuthorityProfile, authority_profile_for_agent

if TYPE_CHECKING:
    from coder_workbench.core.agent_workflow import AgentWorkflowAgent, AgentWorkflowSpec


RoleCardId = Literal["executor", "tester"]
AgentArchetype = Literal["planner", "executor", "tester"]


class RoleCardSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: RoleCardId
    label: str
    archetype: AgentArchetype
    role: str
    default_capabilities: list[str]
    description: str


class AgentRuntimeProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str
    agent_name: str
    role_card: str | None = None
    agent_archetype: str
    authority: AgentAuthorityProfile
    allowed_artifacts: list[str] = Field(default_factory=list)
    context_policy: dict[str, object] = Field(default_factory=dict)
    memory_policy: dict[str, object] = Field(default_factory=dict)
    token_budget: dict[str, object] = Field(default_factory=dict)
    internal_loops: dict[str, object] = Field(default_factory=dict)
    tool_policy: dict[str, object] = Field(default_factory=dict)
    evaluation_profile: dict[str, object] = Field(default_factory=dict)


ROLE_CARDS = [
    RoleCardSpec(
        id="executor",
        label="Executor",
        archetype="executor",
        role="executor",
        default_capabilities=["follow_planner_order", "modify_files", "return_execution_result"],
        description="Perform implementation or execution work assigned by Planner.",
    ),
    RoleCardSpec(
        id="tester",
        label="Tester",
        archetype="tester",
        role="tester",
        default_capabilities=["model_review", "return_test_result"],
        description="Review execution evidence and return test_result facts.",
    ),
]


def role_card_registry() -> dict[str, RoleCardSpec]:
    return {card.id: card for card in ROLE_CARDS}


def role_card_catalog() -> list[dict[str, object]]:
    return [card.model_dump(mode="json") for card in ROLE_CARDS]


def role_card_for_id(role_card_id: str) -> RoleCardSpec:
    try:
        return role_card_registry()[role_card_id]
    except KeyError as exc:
        raise ValueError(f"unknown role_card {role_card_id!r}") from exc


def agent_payload_from_role_card(data: dict[str, object]) -> dict[str, object]:
    migrated = dict(data)
    role_card = data.get("role_card")
    card = role_card_for_id(role_card.strip()) if isinstance(role_card, str) and role_card.strip() else None
    if card is not None and not str(migrated.get("role") or "").strip():
        migrated["role"] = card.role
    capabilities = migrated.get("capabilities")
    if not isinstance(capabilities, list) or not capabilities:
        migrated["capabilities"] = list(card.default_capabilities if card is not None else default_capabilities_for_role(str(migrated.get("role") or "")))
    return migrated


def default_capabilities_for_role(role: str) -> list[str]:
    role = role.strip()
    if role == "planner":
        return [
            "negotiate_contract",
            "make_plan",
            "judge_completion",
            "judge_risk",
            "make_next_decision",
            "round_summarize",
        ]
    if role == "tester":
        return ["model_review", "return_test_result"]
    if role == "executor":
        return ["follow_planner_order", "modify_files", "return_execution_result"]
    return []


def compile_agent_runtime_profile(
    agent: "AgentWorkflowAgent",
    *,
    primary_planner_id: str,
) -> AgentRuntimeProfile:
    authority = authority_profile_for_agent(agent, primary_planner_id=primary_planner_id)
    archetype = _archetype_for_agent(agent, authority.authority)
    return AgentRuntimeProfile(
        agent_id=agent.id,
        agent_name=agent.name,
        role_card=agent.role_card,
        agent_archetype=archetype,
        authority=authority,
        allowed_artifacts=list(authority.allowed_artifact_types),
        context_policy=_context_policy(archetype),
        memory_policy=_memory_policy(authority.authority),
        token_budget=_token_budget(archetype),
        internal_loops=_internal_loops(authority.authority),
        tool_policy=_tool_policy(agent, authority),
        evaluation_profile=_evaluation_profile(archetype),
    )


def compile_runtime_profiles(workflow: "AgentWorkflowSpec") -> list[AgentRuntimeProfile]:
    return [
        compile_agent_runtime_profile(agent, primary_planner_id=workflow.primary_planner_id)
        for agent in workflow.agents
    ]


def _archetype_for_agent(agent: "AgentWorkflowAgent", authority: str) -> str:
    if agent.role_card:
        return role_card_for_id(agent.role_card).archetype
    if authority == "planner":
        return "planner"
    if authority == "tester":
        return "tester"
    return "executor"


def _context_policy(archetype: str) -> dict[str, object]:
    if archetype == "planner":
        return {"skill_load_mode": "index_only", "memory": "workflow_summary", "max_skill_tokens": 0}
    if archetype == "tester":
        return {"skill_load_mode": "selected_summary", "memory": "none", "max_skill_tokens": 800}
    return {"skill_load_mode": "on_demand", "memory": "direct_refs_only", "max_skill_tokens": 1600}


def _memory_policy(authority: str) -> dict[str, object]:
    return {
        "can_read_workflow_memory": authority == "planner",
        "can_write_long_term_memory": authority == "planner",
    }


def _token_budget(archetype: str) -> dict[str, object]:
    budgets = {
        "planner": 12000,
        "executor": 8000,
        "tester": 6000,
    }
    return {"max_input_tokens": budgets.get(archetype, 8000), "managed_by_runtime": True}


def _internal_loops(authority: str) -> dict[str, object]:
    return {
        "schema_repair_attempts": 1,
        "self_check": authority in {"executor", "tester"},
        "planner_repair": authority == "planner",
    }


def _tool_policy(agent: "AgentWorkflowAgent", authority: AgentAuthorityProfile) -> dict[str, object]:
    return {
        "read_files": True,
        "edit_files": authority.can_modify_files and "modify_files" in agent.capabilities,
        "run_commands": authority.can_run_commands and "optional_check_command" in agent.capabilities,
        "external_effects_require_preview": True,
        "connector_operations": "deny_by_default",
    }


def _evaluation_profile(archetype: str) -> dict[str, object]:
    if archetype == "tester":
        return {"artifact_type": "test_result", "metrics": ["evidence_ref_rate", "confidence_calibration"]}
    if archetype == "planner":
        return {"artifact_type": "planner_order", "metrics": ["plan_valid_rate", "wrong_skill_selection_rate"]}
    return {"artifact_type": "execution_result", "metrics": ["schema_valid_rate", "blocked_rate"]}
