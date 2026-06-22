from .budget import ContextBudget, context_compaction_enabled
from .compaction import CompactionResult, ContextCompactor
from .external_refs import ContextExternalRefStore, ExternalRef


def __getattr__(name: str):
    if name in {"AgentContextBuildResult", "ContextService"}:
        from .service import AgentContextBuildResult, ContextService

        return {"AgentContextBuildResult": AgentContextBuildResult, "ContextService": ContextService}[name]
    raise AttributeError(name)

__all__ = [
    "AgentContextBuildResult",
    "CompactionResult",
    "ContextBudget",
    "ContextCompactor",
    "ContextExternalRefStore",
    "ContextService",
    "ExternalRef",
    "context_compaction_enabled",
]
