from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


SkillCapabilityLevel = Literal["index", "summary", "full", "reference"]
SideEffectLevel = Literal["none", "read", "write", "external"]
RiskLevel = Literal["low", "medium", "high"]
MemoryScopeName = Literal["workflow", "project", "user", "persona"]
MemoryAccess = Literal["read", "search", "propose_delta", "write_gated"]


class SkillCapability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill_id: str
    level: SkillCapabilityLevel


class ToolCapability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    toolset: str
    side_effect: SideEffectLevel
    risk: RiskLevel


class ToolRegistryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability: ToolCapability
    description: str = ""
    harness_ids: list[str] = Field(default_factory=list)
    enabled_by_default: bool = True
    requires_approval: bool = False


class McpCapability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    server_id: str
    operation: str
    risk: RiskLevel


class McpManifestOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""
    risk: RiskLevel = "medium"
    side_effect: SideEffectLevel = "external"
    enabled_by_default: bool = False


class McpServerManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    server_id: str
    name: str
    operations: list[McpManifestOperation] = Field(default_factory=list)
    enabled_by_default: bool = False


class McpManifestValidation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    manifest: McpServerManifest | None = None


class MemoryScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: MemoryScopeName
    access: MemoryAccess


class DeniedCapability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    reason: str


class CapabilitySet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skills: list[SkillCapability] = Field(default_factory=list)
    tools: list[ToolCapability] = Field(default_factory=list)
    mcp_operations: list[McpCapability] = Field(default_factory=list)
    memory_scopes: list[MemoryScope] = Field(default_factory=list)
    denied: list[DeniedCapability] = Field(default_factory=list)


__all__ = [
    "CapabilitySet",
    "DeniedCapability",
    "McpCapability",
    "McpManifestOperation",
    "McpManifestValidation",
    "McpServerManifest",
    "MemoryScope",
    "SkillCapability",
    "ToolCapability",
    "ToolRegistryEntry",
]
