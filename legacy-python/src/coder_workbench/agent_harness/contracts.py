from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


HarnessRole = Literal["planner", "executor"]


class HarnessContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    harness_id: str
    role: HarnessRole
    input_artifacts: list[str] = Field(default_factory=list)
    output_artifacts: list[str] = Field(default_factory=list)
    allowed_capability_groups: list[str] = Field(default_factory=list)
    forbidden_capability_groups: list[str] = Field(default_factory=list)
    may_talk_to_user: bool = False
    may_write_files: bool = False
    may_run_commands: bool = False
    may_write_memory: bool = False


PLANNER_ORDER_HARNESS = HarnessContract(
    harness_id="planner-order-harness",
    role="planner",
    input_artifacts=["run_contract", "round_summary", "planner_input_bundle"],
    output_artifacts=["planner_order"],
    allowed_capability_groups=[
        "planner_control",
        "state_read",
        "artifact_inspection",
        "skill_index",
        "memory_read",
    ],
    forbidden_capability_groups=[
        "side_effects",
        "file_write",
        "command_execution",
        "external_publish",
        "direct_memory_write",
    ],
)

PLANNER_DECISION_HARNESS = HarnessContract(
    harness_id="planner-decision-harness",
    role="planner",
    input_artifacts=["planner_input_bundle", "round_summary", "execution_result"],
    output_artifacts=["planner_decision"],
    allowed_capability_groups=[
        "planner_control",
        "state_read",
        "artifact_inspection",
        "evidence_read",
        "memory_read",
    ],
    forbidden_capability_groups=[
        "side_effects",
        "file_write",
        "command_execution",
        "external_publish",
        "direct_memory_write",
    ],
)

FINAL_REPORT_HARNESS = HarnessContract(
    harness_id="final-report-harness",
    role="planner",
    input_artifacts=["planner_decision", "round_summary", "execution_result"],
    output_artifacts=["final_report"],
    allowed_capability_groups=[
        "planner_control",
        "state_read",
        "artifact_inspection",
        "evidence_read",
        "memory_read",
    ],
    forbidden_capability_groups=[
        "file_write",
        "command_execution",
        "external_publish",
        "direct_memory_write",
    ],
    may_talk_to_user=True,
)

CODE_WORKER_HARNESS = HarnessContract(
    harness_id="code-worker-harness",
    role="executor",
    input_artifacts=["planner_order"],
    output_artifacts=["execution_result"],
    allowed_capability_groups=[
        "project_read",
        "project_write_preview",
        "sandbox_command",
        "tool_output_read",
        "artifact_write",
    ],
    forbidden_capability_groups=[
        "ask_user",
        "final_report",
        "direct_memory_write",
        "external_publish",
        "plugin_install",
        "mcp_enable",
    ],
    may_write_files=True,
    may_run_commands=True,
)

HARNESS_CONTRACTS = {
    contract.harness_id: contract
    for contract in (
        PLANNER_ORDER_HARNESS,
        PLANNER_DECISION_HARNESS,
        FINAL_REPORT_HARNESS,
        CODE_WORKER_HARNESS,
    )
}


def harness_contract_for_id(harness_id: str) -> HarnessContract:
    try:
        return HARNESS_CONTRACTS[harness_id]
    except KeyError as exc:
        raise ValueError(f"unknown harness_id {harness_id!r}") from exc


def harness_contracts_for_role(role: HarnessRole) -> list[HarnessContract]:
    return [contract for contract in HARNESS_CONTRACTS.values() if contract.role == role]


__all__ = [
    "CODE_WORKER_HARNESS",
    "FINAL_REPORT_HARNESS",
    "HARNESS_CONTRACTS",
    "HarnessContract",
    "PLANNER_DECISION_HARNESS",
    "PLANNER_ORDER_HARNESS",
    "harness_contract_for_id",
    "harness_contracts_for_role",
]
