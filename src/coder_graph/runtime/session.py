from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from coder_graph.models import AgentCard


class ToolCall(BaseModel):
    """A tool request made by one agent session.

    Execution is intentionally separate from the request. This lets the UI and
    permission policy review high-risk operations before they mutate anything.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: str(uuid4()))
    agent_id: str
    name: str
    arguments: dict = Field(default_factory=dict)
    status: Literal["requested", "approved", "rejected", "completed", "failed"] = "requested"
    result: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PermissionPolicy(BaseModel):
    """Per-agent permission gates for Claude Code-like capabilities."""

    model_config = ConfigDict(extra="forbid")

    read_files: bool = True
    edit_files: bool = False
    run_commands: bool = False
    use_network: bool = False
    requires_approval: bool = True

    @classmethod
    def from_agent(cls, agent: AgentCard) -> "PermissionPolicy":
        return cls.model_validate(agent.runtime.permissions)

    def allows_tool(self, tool_name: str) -> bool:
        if tool_name in {"read", "search"}:
            return self.read_files
        if tool_name in {"edit", "write", "patch"}:
            return self.edit_files
        if tool_name in {"shell", "command"}:
            return self.run_commands
        if tool_name in {"network", "fetch", "web"}:
            return self.use_network
        return False


class AgentSession(BaseModel):
    """Runtime state owned by a single agent workbench."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: str(uuid4()))
    agent_id: str
    status: Literal["idle", "running", "waiting_for_approval", "completed", "failed"] = "idle"
    inbox: list[str] = Field(default_factory=list)
    outbox: list[str] = Field(default_factory=list)
    tool_calls: list[ToolCall] = Field(default_factory=list)
    memory: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def for_agent(cls, agent: AgentCard) -> "AgentSession":
        return cls(
            id=agent.runtime.session_id or str(uuid4()),
            agent_id=agent.id,
            memory=agent.runtime.memory,
        )

    def request_tool(self, tool_name: str, arguments: dict | None = None) -> ToolCall:
        call = ToolCall(agent_id=self.agent_id, name=tool_name, arguments=arguments or {})
        self.tool_calls.append(call)
        self.updated_at = datetime.now(timezone.utc)
        return call


class AgentRuntime(BaseModel):
    """A conservative adapter boundary for future Claude Code-like runners."""

    model_config = ConfigDict(extra="forbid")

    agent: AgentCard
    session: AgentSession
    permission_policy: PermissionPolicy

    @classmethod
    def from_agent(cls, agent: AgentCard) -> "AgentRuntime":
        return cls(
            agent=agent,
            session=AgentSession.for_agent(agent),
            permission_policy=PermissionPolicy.from_agent(agent),
        )

    def can_use_tool(self, tool_name: str) -> bool:
        return self.permission_policy.allows_tool(tool_name)
