from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from coder_workbench.agent_model import TokenBudget


class HarnessBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    type: Literal[
        "context_builder",
        "skill_loader",
        "model_loop",
        "tool_gate",
        "patch_preview",
        "sandbox_check",
        "artifact_validator",
        "repair_once",
        "self_check",
        "interrupt_gate",
        "planner_decision",
        "output_artifact",
    ]
    config: dict[str, Any] = Field(default_factory=dict)


class HarnessGraph(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes: list[HarnessBlock]
    edges: list[tuple[str, str]] = Field(default_factory=list)


class AgentEngineSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    engine_type: Literal["planner", "worker", "tester", "final_tester", "custom"]
    description: str = ""
    harness_graph: HarnessGraph
    allowed_artifacts: list[str] = Field(default_factory=list)
    allowed_plugins: list[str] = Field(default_factory=list)
    allowed_skill_types: list[str] = Field(default_factory=list)
    token_budget: TokenBudget
    can_ask_human: bool = False
    can_write_files: bool = False
    can_run_commands: bool = False
    can_write_memory: bool = False
