from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .agent import AgentCard


class WorkflowStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: Literal["agent", "deterministic", "human_gate"]
    uses: str
    input_keys: list[str] = Field(default_factory=list)
    output_key: str


class WorkflowEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    target: str
    condition: str | None = None


class WorkflowSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str = ""
    max_loops: int = Field(default=3, ge=1, le=10)
    agents: list[AgentCard] = Field(default_factory=list)
    steps: list[WorkflowStep] = Field(default_factory=list)
    edges: list[WorkflowEdge] = Field(default_factory=list)
    stop_conditions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_references(self) -> "WorkflowSpec":
        agent_ids = {agent.id for agent in self.agents}
        step_ids = {step.id for step in self.steps}

        for step in self.steps:
            if step.kind == "agent" and step.uses not in agent_ids:
                raise ValueError(f"step {step.id} references unknown agent: {step.uses}")

        for edge in self.edges:
            if edge.source not in step_ids and edge.source not in agent_ids:
                raise ValueError(f"edge source not found: {edge.source}")
            if edge.target not in step_ids and edge.target not in agent_ids:
                raise ValueError(f"edge target not found: {edge.target}")

        return self

