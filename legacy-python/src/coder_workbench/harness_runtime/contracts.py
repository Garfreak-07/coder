from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


CONVERSATION_HARNESS_ID = "conversation-harness"
TASK_EXECUTION_HARNESS_ID = "task-execution-harness"

HarnessRole = Literal["planner", "executor"]
HarnessMode = Literal["planning_chat", "workflow_supervisor", "task_execution"]

LEGACY_HARNESS_ALIASES: dict[str, tuple[str, HarnessMode]] = {
    "planner-order-harness": (CONVERSATION_HARNESS_ID, "workflow_supervisor"),
    "planner-decision-harness": (CONVERSATION_HARNESS_ID, "workflow_supervisor"),
    "final-report-harness": (CONVERSATION_HARNESS_ID, "workflow_supervisor"),
    "code-worker-harness": (TASK_EXECUTION_HARNESS_ID, "task_execution"),
}


class HarnessContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    harness_id: str
    role: HarnessRole
    modes: list[HarnessMode] = Field(default_factory=list)
    input_artifacts: list[str] = Field(default_factory=list)
    output_artifacts: list[str] = Field(default_factory=list)
    may_talk_to_user: bool = False
    may_write_files: bool = False
    may_run_commands: bool = False
    may_write_memory: bool = False
    may_publish_external: bool = False


CONVERSATION_HARNESS = HarnessContract(
    harness_id=CONVERSATION_HARNESS_ID,
    role="planner",
    modes=["planning_chat", "workflow_supervisor"],
    input_artifacts=[
        "user_request",
        "project_plan_draft",
        "run_contract",
        "planner_input_bundle",
        "round_summary",
        "execution_result",
    ],
    output_artifacts=[
        "project_plan_draft",
        "run_contract_draft",
        "planner_order",
        "planner_decision",
        "final_report",
    ],
    may_talk_to_user=True,
)

TASK_EXECUTION_HARNESS = HarnessContract(
    harness_id=TASK_EXECUTION_HARNESS_ID,
    role="executor",
    modes=["task_execution"],
    input_artifacts=[
        "planner_order",
        "work_item",
        "agent_task_envelope",
    ],
    output_artifacts=["execution_result"],
    may_write_files=True,
    may_run_commands=True,
)

HARNESS_CONTRACTS: dict[str, HarnessContract] = {
    CONVERSATION_HARNESS.harness_id: CONVERSATION_HARNESS,
    TASK_EXECUTION_HARNESS.harness_id: TASK_EXECUTION_HARNESS,
}


def resolve_harness_id(harness_id: str) -> tuple[str, HarnessMode | None]:
    """Resolve legacy harness IDs to the canonical harness contract and mode."""

    if harness_id in HARNESS_CONTRACTS:
        return harness_id, None
    if harness_id in LEGACY_HARNESS_ALIASES:
        return LEGACY_HARNESS_ALIASES[harness_id]
    raise ValueError(f"unknown harness_id {harness_id!r}")


def harness_contract_for_id(harness_id: str) -> HarnessContract:
    canonical_id, _mode = resolve_harness_id(harness_id)
    return HARNESS_CONTRACTS[canonical_id]


def harness_contracts_for_role(role: HarnessRole) -> list[HarnessContract]:
    return [contract for contract in HARNESS_CONTRACTS.values() if contract.role == role]


__all__ = [
    "CONVERSATION_HARNESS",
    "CONVERSATION_HARNESS_ID",
    "HARNESS_CONTRACTS",
    "LEGACY_HARNESS_ALIASES",
    "TASK_EXECUTION_HARNESS",
    "TASK_EXECUTION_HARNESS_ID",
    "HarnessContract",
    "HarnessMode",
    "HarnessRole",
    "harness_contract_for_id",
    "harness_contracts_for_role",
    "resolve_harness_id",
]
