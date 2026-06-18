from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AgentCard(BaseModel):
    """A small Agent Card inspired by A2A-style capability descriptions."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str | None = None
    role: str
    goal: str
    instructions: str = ""
    skills: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    input_keys: list[str] = Field(default_factory=list)
    output_schema: dict[str, str] = Field(default_factory=dict)
    stop_rules: list[str] = Field(default_factory=list)
    model: str | None = None

    def display_name(self) -> str:
        return self.name or self.id

